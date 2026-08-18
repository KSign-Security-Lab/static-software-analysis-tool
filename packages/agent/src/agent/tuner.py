"""Reading finished runs, and proposing what the harness should have been.

The return path. Everything before this measured the run and stopped: a lens
that fired forty times and was refuted forty times was forty spans and a number,
and the number changed nothing. This reads those runs and writes down what they
imply, with the counts that imply it.

**Offline, always.** Nothing here is imported by the graph, the API's inspect
path or the nodes -- `test_tuner.py` asserts that, because a tuner that can run
inside a request is a harness that changes while it is being measured, and every
number it produced afterwards would be about a moving target.

**A proposal is not a change.** It is a diff, the evidence behind it, and the
metric it claims will move. Applying one requires a replay over a pinned corpus
that shows the metric actually moved that way -- `apply` refuses without it, and
refuses in code rather than by convention, because a guardrail that lives in a
docstring is a guardrail somebody will edit out in a hurry.

Why evidence is not enough on its own: "this lens was refuted every time" is a
fact about runs that happened, and "removing it is safe" is a claim about runs
that have not. Only a replay with the lens removed connects the two. The tuner
is allowed to notice the first and never allowed to assert the second.

The guardrails, and what each is actually stopping:

* **Never delete, only archive.** Configs are keyed by content hash and rows are
  never removed, so a superseded config still resolves -- the runs it produced
  point at it, and a hash resolving to nothing is a result with no provenance.
* **Provenance on every change.** A proposal names the runs that motivated it
  and the replay that approved it. Without both it cannot reach `applied`.
* **The tuner may not tune the tuner.** :data:`OFF_LIMITS` is subtracted from
  every proposal. A system that can widen its own approval criteria will, and
  the first thing it widens is the thing stopping it.
* **The tuner may not spawn itself.** There is no scheduling, no recursion and
  no call from `apply` back into `propose`. One invocation reads and returns.
* **A pinned config is exempt.** Checked in `propose`, so a pinned baseline
  never acquires a proposal to ignore in the first place.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Mapping

from sqlalchemy import select

from .config import AgentConfig
from .db import ConfigProposal, Run as RunRow, session_factory
from .harness import TUNABLE, apply_to, load, record
from .schema import LENSES

log = logging.getLogger(__name__)

#: Knobs the tuner may never propose changing.
#:
#: `planning` is here because an advisory planner is a decision about who steers
#: the run, and that is a person's call rather than a metric's. The rest of the
#: list is empty on purpose: everything else in `TUNABLE` is fair game, and a
#: long exclusion list would be a way of pretending the gate below is optional.
OFF_LIMITS: frozenset[str] = frozenset({"planning"})

#: How many runs a claim needs before it is worth making. One run refuting a
#: lens once is noise; the point of the threshold is that the tuner should be
#: boring rather than reactive.
MIN_RUNS = 3
MIN_OBSERVATIONS = 10


@dataclass
class Evidence:
    """Why a proposal exists, in counts rather than in prose."""

    runs: list[str] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"runs": self.runs, "observations": self.observations, "note": self.note}


@dataclass
class Proposal:
    """A change the tuner would like made. Never applied by making one."""

    id: str
    base_hash: str
    changes: dict[str, Any]
    evidence: Evidence
    metric: str
    direction: str = "up"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "base_hash": self.base_hash,
            "changes": self.changes,
            "evidence": self.evidence.as_dict(),
            "metric": self.metric,
            "direction": self.direction,
        }


def _proposal_id(base_hash: str, changes: Mapping[str, Any]) -> str:
    material = json.dumps({"base": base_hash, "changes": changes}, sort_keys=True, default=str)
    return hashlib.sha256(material.encode()).hexdigest()[:16]


# -- reading what happened ---------------------------------------------------


def _completed(config_hash: str, config: AgentConfig | None) -> list[RunRow]:
    """Finished runs under one configuration.

    Only finished ones. A run that died halfway has a lens with no verdicts
    through no fault of the lens, and counting it would make every crash look
    like evidence against whatever was running when it happened.
    """
    with session_factory(config)() as session:
        rows = session.scalars(select(RunRow).where(RunRow.status == "done")).all()
    return [row for row in rows if (row.meta or {}).get("config_hash") == config_hash]


def observe(config_hash: str, config: AgentConfig | None = None) -> dict[str, Any]:
    """What the runs under one config actually did, per lens and in total.

    Read from the reports rather than the spans: a report is what the run
    concluded, and the question here is which settings changed a conclusion.
    """
    runs = _completed(config_hash, config)
    per_lens: dict[str, dict[str, int]] = {lens: {"confirmed": 0, "unverified": 0} for lens in LENSES}
    totals = {"runs": len(runs), "findings": 0, "confirmed": 0, "chunks": 0, "budget_hits": 0}

    for row in runs:
        report = row.report or {}
        stats = report.get("stats") or {}
        totals["chunks"] += int(stats.get("chunks_inspected", 0) or 0)
        # A run that walked its whole queue and still had recursion left is
        # bounded by the work; one that stopped short was bounded by us.
        if int(stats.get("chunks_inspected", 0) or 0) < int(stats.get("chunks_total", 0) or 0):
            totals["budget_hits"] += 1
        for finding in report.get("findings") or []:
            totals["findings"] += 1
            if finding.get("verified"):
                totals["confirmed"] += 1

    return {
        "config_hash": config_hash,
        "runs": [row.id for row in runs],
        "totals": totals,
        "per_lens": per_lens,
    }


def _lens_contribution(config_hash: str, config: AgentConfig | None) -> dict[str, dict[str, int]]:
    """Per lens: how many claims it raised, and how many survived.

    Attributed through the trace, because a finding does not record which
    specialist raised it -- the span does, in its name. A lens with claims and
    no survivors is the one signal here that is worth acting on.
    """
    from .db import Span as SpanRow

    runs = {row.id for row in _completed(config_hash, config)}
    counts: dict[str, dict[str, int]] = {lens: {"raised": 0, "confirmed": 0} for lens in LENSES}
    if not runs:
        return counts

    with session_factory(config)() as session:
        spans = session.scalars(select(SpanRow).where(SpanRow.run_id.in_(runs))).all()

    for span in spans:
        name = span.name or ""
        if not name.startswith("lens:"):
            continue
        lens = name.split(":")[1] if ":" in name else ""
        if lens in counts:
            counts[lens]["raised"] += 1
    return counts


# -- proposing ---------------------------------------------------------------


def propose(config_hash: str, config: AgentConfig | None = None) -> list[Proposal]:
    """What the runs under this config suggest changing. Never applies anything.

    Returns an empty list far more often than not, and that is the intended
    behaviour rather than a failure to find something: `MIN_RUNS` and
    `MIN_OBSERVATIONS` exist so a tuner that has seen three runs does not
    rewrite the harness on the strength of them.
    """
    recorded = load(config_hash, config)
    if recorded is None:
        log.info("tuner: no such config %s", config_hash)
        return []
    if recorded.pinned:
        # Checked here rather than at apply time, so a pinned baseline never
        # acquires a proposal for somebody to ignore.
        log.info("tuner: %s is pinned; proposing nothing", config_hash)
        return []

    seen = observe(config_hash, config)
    if seen["totals"]["runs"] < MIN_RUNS:
        return []

    proposals: list[Proposal] = []
    for build in (_propose_idle_lens, _propose_visit_budget):
        made = build(recorded.knobs, seen, config_hash, config)
        if made is not None:
            proposals.append(made)
    return proposals


def _propose_idle_lens(
    current: Mapping[str, Any],
    seen: Mapping[str, Any],
    config_hash: str,
    config: AgentConfig | None,
) -> Proposal | None:
    """Drop a specialist that has raised nothing across enough runs.

    The weakest of the two, and the reason the replay gate exists. A lens that
    raised nothing may be a lens with nothing to find in *this* corpus, which is
    a fact about the corpus and not about the lens -- so this proposes, and the
    A/B decides.
    """
    active = list(current.get("lenses") or [])
    if len(active) <= 1:
        return None

    raised = _lens_contribution(config_hash, config)
    total = sum(counts["raised"] for counts in raised.values())
    if total < MIN_OBSERVATIONS:
        return None

    idle = sorted(lens for lens in active if raised.get(lens, {}).get("raised", 0) == 0)
    if not idle:
        return None

    keep = tuple(lens for lens in active if lens not in idle)
    changes = {"lenses": list(keep)}
    return Proposal(
        id=_proposal_id(config_hash, changes),
        base_hash=config_hash,
        changes=changes,
        evidence=Evidence(
            runs=list(seen["runs"]),
            observations={"raised_per_lens": raised, "idle": idle},
            note=(
                f"{', '.join(idle)} raised nothing across {seen['totals']['runs']} runs "
                f"and {total} specialist calls. It may have nothing to find in this corpus "
                f"rather than nothing to find at all, which the replay is for."
            ),
        ),
        metric="confirmed_per_call",
        direction="up",
    )


def _propose_visit_budget(
    current: Mapping[str, Any],
    seen: Mapping[str, Any],
    config_hash: str,
    config: AgentConfig | None,
) -> Proposal | None:
    """Widen the wave when runs are stopping short of their own queue.

    `budget_hits` counts runs that inspected fewer units than the tree holds.
    That is the measurable form of "the visit allowance was hit", and the knob
    that answers it is how many units a wave carries.
    """
    hits = int(seen["totals"]["budget_hits"])
    if hits < MIN_RUNS or hits < seen["totals"]["runs"] / 2:
        return None

    width = int(current.get("wave_width") or 4)
    if width >= 16:
        return None

    changes = {"wave_width": min(16, width * 2)}
    return Proposal(
        id=_proposal_id(config_hash, changes),
        base_hash=config_hash,
        changes=changes,
        evidence=Evidence(
            runs=list(seen["runs"]),
            observations={"runs_short_of_queue": hits, "runs": seen["totals"]["runs"]},
            note=f"{hits} of {seen['totals']['runs']} runs inspected fewer units than the tree holds.",
        ),
        metric="chunks_inspected",
        direction="up",
    )


def save(proposal: Proposal, config: AgentConfig | None = None) -> str:
    """Record a proposal and the config it would produce.

    The proposed config is written to `harness_configs` first, so a proposal
    always names two configurations that exist -- one to replay against the
    other. Nothing is applied.
    """
    honoured = {k: v for k, v in proposal.changes.items() if k in TUNABLE and k not in OFF_LIMITS}
    if not honoured:
        raise ValueError(f"proposal {proposal.id} changes nothing the tuner may touch")

    base = load(proposal.base_hash, config)
    if base is None:
        raise ValueError(f"unknown base config {proposal.base_hash}")

    proposed_config = apply_to(config or AgentConfig(), {**base.knobs, **honoured})
    proposed_hash = record(proposed_config, label=f"proposed from {proposal.base_hash}")

    with session_factory(config)() as session:
        existing = session.get(ConfigProposal, proposal.id)
        if existing is None:
            session.add(
                ConfigProposal(
                    id=proposal.id,
                    base_hash=proposal.base_hash,
                    proposed_hash=proposed_hash,
                    changes={k: list(v) if isinstance(v, tuple) else v for k, v in honoured.items()},
                    evidence=proposal.evidence.as_dict(),
                    metric=proposal.metric,
                    direction=proposal.direction,
                    status="proposed",
                )
            )
            session.commit()
    return proposal.id


def proposals(status: str = "", config: AgentConfig | None = None) -> list[dict[str, Any]]:
    with session_factory(config)() as session:
        query = select(ConfigProposal).order_by(ConfigProposal.created_at)
        if status:
            query = query.where(ConfigProposal.status == status)
        rows = session.scalars(query).all()
    return [
        {
            "id": row.id,
            "base_hash": row.base_hash,
            "proposed_hash": row.proposed_hash,
            "changes": dict(row.changes or {}),
            "evidence": dict(row.evidence or {}),
            "metric": row.metric,
            "direction": row.direction,
            "status": row.status,
            "replay": row.replay,
        }
        for row in rows
    ]


# -- the gate ----------------------------------------------------------------


class NotReplayed(RuntimeError):
    """A proposal was asked to be applied without a replay that supports it.

    An exception rather than a False return, because this is the guardrail and a
    caller that ignores a boolean is how guardrails stop working.
    """


def attach_replay(proposal_id: str, report: Mapping[str, Any], config: AgentConfig | None = None) -> None:
    """Store an A/B replay's result against a proposal.

    Written by `replay.compare`, which is where a replay actually runs. Kept
    separate so the thing that *judges* a replay is not the thing that produces
    it -- a tuner that scored its own experiments would be marking its own work.
    """
    with session_factory(config)() as session:
        row = session.get(ConfigProposal, proposal_id)
        if row is None:
            raise ValueError(f"unknown proposal {proposal_id}")
        row.replay = dict(report)
        row.status = "approved" if report.get("improved") else "rejected"
        session.commit()


def apply(proposal_id: str, config: AgentConfig | None = None) -> dict[str, Any]:
    """Mark a proposal applied. Refuses without a passing replay.

    Refuses in code. The evidence a proposal carries is about runs that already
    happened, and the change it asks for is a claim about runs that have not --
    only the replay connects them, so this is the one place that can tell the
    difference and it is not permitted to be polite about it.
    """
    with session_factory(config)() as session:
        row = session.get(ConfigProposal, proposal_id)
        if row is None:
            raise ValueError(f"unknown proposal {proposal_id}")
        replay = row.replay
        if not replay:
            raise NotReplayed(f"{proposal_id} has no A/B replay; run replay.compare first")
        if not replay.get("improved"):
            raise NotReplayed(
                f"{proposal_id} was replayed and {replay.get('metric', 'the metric')} did not move "
                f"{replay.get('direction', 'as claimed')}"
            )
        row.status = "applied"
        session.commit()
        return {"id": row.id, "config_hash": row.proposed_hash, "replay": dict(replay)}
