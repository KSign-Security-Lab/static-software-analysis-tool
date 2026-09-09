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
from .mcp.client import LENS_TOOLS
from .schema import LENSES

log = logging.getLogger(__name__)
OFF_LIMITS: frozenset[str] = frozenset({"planning"})
MIN_RUNS = 3
MIN_OBSERVATIONS = 10


@dataclass
class Evidence:
    runs: list[str] = field(default_factory=list)
    observations: dict[str, Any] = field(default_factory=dict)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"runs": self.runs, "observations": self.observations, "note": self.note}


@dataclass
class Proposal:
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


def _completed(config_hash: str, config: AgentConfig | None) -> list[RunRow]:
    with session_factory(config)() as session:
        rows = session.scalars(select(RunRow).where(RunRow.status == "done")).all()
    return [
        row
        for row in rows
        if (row.meta or {}).get("config_hash") == config_hash and not (row.meta or {}).get("replay")
    ]


def observe(config_hash: str, config: AgentConfig | None = None) -> dict[str, Any]:
    runs = _completed(config_hash, config)
    totals = {"runs": len(runs), "findings": 0, "confirmed": 0, "chunks": 0, "budget_hits": 0}

    for row in runs:
        report = row.report or {}
        stats = report.get("stats") or {}
        totals["chunks"] += int(stats.get("chunks_inspected", 0) or 0)
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
    }


def _lens_record(config_hash: str, config: AgentConfig | None) -> dict[str, dict[str, int]]:
    from .db import Span as SpanRow

    runs = _completed(config_hash, config)
    ids = {row.id for row in runs}
    counts: dict[str, dict[str, int]] = {
        lens: {"calls": 0, "raised": 0, "confirmed": 0} for lens in LENSES
    }
    if not ids:
        return counts

    with session_factory(config)() as session:
        spans = session.scalars(select(SpanRow).where(SpanRow.run_id.in_(ids))).all()
    for span in spans:
        name = span.name or ""
        if not name.startswith("lens:"):
            continue
        lens = name.split(":")[1] if ":" in name else ""
        if lens in counts:
            counts[lens]["calls"] += 1

    for row in runs:
        for finding in (row.report or {}).get("findings") or []:
            lens = finding.get("lens")
            if lens not in counts:
                continue
            counts[lens]["raised"] += 1
            if finding.get("verified"):
                counts[lens]["confirmed"] += 1
    return counts


def _tool_record(config_hash: str, config: AgentConfig | None) -> dict[str, int]:
    from .db import Span as SpanRow

    ids = {row.id for row in _completed(config_hash, config)}
    counts: dict[str, int] = {}
    if not ids:
        return counts
    with session_factory(config)() as session:
        spans = session.scalars(
            select(SpanRow).where(SpanRow.run_id.in_(ids), SpanRow.kind == "tool")
        ).all()
    for span in spans:
        counts[span.name or "?"] = counts.get(span.name or "?", 0) + 1
    return counts


def propose(config_hash: str, config: AgentConfig | None = None) -> list[Proposal]:
    recorded = load(config_hash, config)
    if recorded is None:
        log.info("tuner: no such config %s", config_hash)
        return []
    if recorded.pinned:
        log.info("tuner: %s is pinned; proposing nothing", config_hash)
        return []

    seen = observe(config_hash, config)
    if seen["totals"]["runs"] < MIN_RUNS:
        return []

    proposals: list[Proposal] = []
    for build in (_propose_idle_lens, _propose_visit_budget, _propose_tool_budget):
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
    active = list(current.get("lenses") or [])
    if len(active) <= 1:
        return None

    record_by_lens = _lens_record(config_hash, config)
    total_calls = sum(counts["calls"] for counts in record_by_lens.values())
    if total_calls < MIN_OBSERVATIONS:
        return None

    refuted, silent = [], []
    for lens in active:
        counts = record_by_lens.get(lens, {"calls": 0, "raised": 0, "confirmed": 0})
        if counts["calls"] == 0:
            silent.append(lens)
        elif counts["raised"] >= MIN_OBSERVATIONS and counts["confirmed"] == 0:
            refuted.append(lens)

    idle = sorted(refuted + silent)
    if not idle or len(idle) >= len(active):
        return None

    keep = tuple(lens for lens in active if lens not in idle)
    changes = {"lenses": list(keep)}
    reasons = []
    if refuted:
        reasons.append(
            ", ".join(
                f"{lens} raised {record_by_lens[lens]['raised']} and had none confirmed" for lens in sorted(refuted)
            )
        )
    if silent:
        reasons.append(f"{', '.join(sorted(silent))} was never called -- triage routed nothing to it")

    return Proposal(
        id=_proposal_id(config_hash, changes),
        base_hash=config_hash,
        changes=changes,
        evidence=Evidence(
            runs=list(seen["runs"]),
            observations={"per_lens": record_by_lens, "refuted_throughout": refuted, "never_called": silent},
            note=(
                f"Across {seen['totals']['runs']} runs and {total_calls} specialist calls: "
                f"{'; '.join(reasons)}."
            ),
        ),
        metric="confirmed_per_call",
        direction="up",
    )


def _propose_tool_budget(
    current: Mapping[str, Any],
    seen: Mapping[str, Any],
    config_hash: str,
    config: AgentConfig | None,
) -> Proposal | None:
    budget = int(current.get("max_lens_tool_calls") or 0)
    if budget <= 1 or not current.get("lens_tools"):
        return None
    if seen["totals"]["confirmed"] < 1:
        return None

    tools = _tool_record(config_hash, config)
    lens_tools = {name: n for name, n in tools.items() if name in set(LENS_TOOLS)}
    if sum(lens_tools.values()) > 0:
        return None

    changes = {"max_lens_tool_calls": 0, "lens_tools": False}
    return Proposal(
        id=_proposal_id(config_hash, changes),
        base_hash=config_hash,
        changes=changes,
        evidence=Evidence(
            runs=list(seen["runs"]),
            observations={"tool_calls": tools, "lens_tool_calls": lens_tools, "budget": budget},
            note=(
                f"The specialists were offered {budget} lookups each across {seen['totals']['runs']} runs "
                f"and took none, while {seen['totals']['confirmed']} findings were confirmed without them."
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


class NotReplayed(RuntimeError):
    pass


def attach_replay(proposal_id: str, report: Mapping[str, Any], config: AgentConfig | None = None) -> None:
    with session_factory(config)() as session:
        row = session.get(ConfigProposal, proposal_id)
        if row is None:
            raise ValueError(f"unknown proposal {proposal_id}")
        row.replay = dict(report)
        row.status = "approved" if report.get("improved") else "rejected"
        session.commit()


def apply(proposal_id: str, config: AgentConfig | None = None) -> dict[str, Any]:
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
