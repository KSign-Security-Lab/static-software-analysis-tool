"""The nodes of the inspection loop, and the routers that fan them out.

    plan -> context -> triage -> {memory, injection, access, logic}
         -> locate -> verify -> reduce -> (next wave, or done)

Three things happen at once here, and each is a different kind of parallelism.
A *wave* is several chunks at one call depth, which by construction cannot need
each other's notes. A *lens* is one of four specialists looking at one chunk for
its own family of defect. A *verify* is one claim being refuted. All three fan
out through LangGraph's `Send`, so the graph shows what is actually in flight
rather than one node that takes a long time.

Built by :func:`make_nodes` so they close over the store, the model client and
the run root instead of carrying them in graph state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, Sequence

from langgraph.types import Send

from ..config import AgentConfig
from ..context import ContextPack, build_context
from ..ids import finding_id, normalize_cwe
from ..index.chunk import Chunk
from ..index.order import wave as pick_wave
from ..index.store import ChunkStore
from ..llm import StructuredCaller
from ..locate import locate_anchor
from ..prompts import analyse_user, gather_user, triage_user, verify_user
from ..promptstore import DEFAULTS as DEFAULT_PROMPTS
from ..promptstore import lens_prompt
from ..tracing import call_config
from ..schema import (
    LENSES,
    CandidateFinding,
    ChunkAnalysis,
    Evidence,
    Finding,
    Lens,
    Remediation,
    Triage,
    Verdict,
)
from .state import InspectionState, clear_wave

log = logging.getLogger(__name__)


class ProgressSink(Protocol):
    """Where progress events go. The API turns these into SSE."""

    def __call__(self, event: str, payload: dict[str, Any]) -> None: ...


class InspectionNode(Protocol):
    """LangGraph's node protocol requires the parameter to be *named* ``state``,
    which a plain ``Callable`` does not satisfy."""

    def __call__(self, state: InspectionState) -> dict[str, Any]: ...


def _noop(event: str, payload: dict[str, Any]) -> None:
    return None


@dataclass
class NodeDeps:
    """Everything the nodes need that does not belong in graph state."""

    store: ChunkStore
    config: AgentConfig
    caller: StructuredCaller
    root: Path
    emit: ProgressSink = _noop
    # Tags traces, so a LangSmith run maps back to a report.
    run_id: str = ""
    # None means verification runs from context alone -- a supported mode, not a
    # degraded one.
    tools: Any = None
    # System prompts for this run, keyed by step. Resolved once when the run
    # starts rather than read per call, so a prompt edited mid-run cannot leave
    # half the chunks analysed against one prompt and half against another.
    prompts: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PROMPTS))
    # Chunk id to subsystem, from the run's knowledge graph. Decides who shares
    # a wave with whom: four related functions read better than four strangers,
    # and they share callees, so the context cache is already warm.
    subsystems: dict[str, int] = field(default_factory=dict)
    # One assembled pack per chunk, for this run. Four specialists and a
    # verifier all want the same one; building it is deterministic and cheap,
    # but not free, and doing it five times says something untrue about the
    # cost of a lens.
    _packs: dict[str, ContextPack] = field(default_factory=dict, repr=False)

    def pack_for(self, chunk: Chunk) -> ContextPack:
        cached = self._packs.get(chunk.chunk_id)
        if cached is None:
            cached = build_context(self.store, chunk, self.config)
            self._packs[chunk.chunk_id] = cached
        return cached


# A title is a UI chip; a paragraph wraps the panel and truncates the tooltip.
MAX_TITLE_CHARS = 120


def _clean_title(raw: str) -> str:
    """Collapse a title to one line, and bound it."""
    collapsed = " ".join(raw.split())
    if len(collapsed) <= MAX_TITLE_CHARS:
        return collapsed or "Unnamed finding"
    return collapsed[: MAX_TITLE_CHARS - 1].rstrip() + "…"


def _finding_subject(finding: Finding) -> str:
    """Label for the trace span name."""
    where = f"{finding.primary.file}:{finding.primary.start_line}"
    return f"{finding.cwe} {where}" if finding.cwe else where


def _file_text(root: Path, relative: str) -> str | None:
    try:
        return (root / relative).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _locate_candidate(
    candidate: CandidateFinding,
    chunk: Chunk,
    deps: NodeDeps,
) -> Finding | None:
    """Resolve a candidate's anchors, or discard it.

    The primary anchor is mandatory. Evidence anchors are best-effort: losing
    one weakens the explanation but does not invalidate the finding.
    """
    text = _file_text(deps.root, chunk.file)
    if text is None:
        return None

    primary = locate_anchor(candidate.anchor_text, chunk.file, text, chunk)
    if primary is None:
        # The anchor, not the title: the anchor is what failed.
        log.info(
            "dropping finding in %s :: %s -- anchor not found: %r",
            chunk.file,
            chunk.symbol,
            candidate.anchor_text[:200],
        )
        return None

    evidence: list[Evidence] = []
    for item in candidate.evidence:
        # Evidence may point at another file: the cross-file trail.
        item_text = text if item.file == chunk.file else _file_text(deps.root, item.file)
        if item_text is None:
            continue
        window = chunk if item.file == chunk.file else None
        located = locate_anchor(item.anchor_text, item.file, item_text, window)
        if located is not None:
            evidence.append(Evidence(role=item.role, span=located.span, note=item.note))

    # Before the id, so "CWE-78" and a prose blob hash the same.
    cwe = normalize_cwe(candidate.cwe)

    return Finding(
        id=finding_id(
            file=chunk.file,
            symbol=chunk.symbol,
            cwe=cwe,
            anchor_text=candidate.anchor_text,
        ),
        chunk_id=chunk.chunk_id,
        severity=candidate.severity,
        confidence=0.5,
        title=_clean_title(candidate.title),
        cwe=cwe,
        primary=primary.span,
        explanation=candidate.explanation,
        evidence=evidence,
        remediation=Remediation(
            summary=candidate.remediation.summary,
            detail=candidate.remediation.detail,
        ),
        verified=False,
    )


def make_nodes(deps: NodeDeps) -> dict[str, InspectionNode]:
    """Build the node functions, bound to one run's dependencies."""

    def _chunk(state: Any) -> Chunk | None:
        chunk_id = state.get("chunk_id")
        return deps.store.chunk(chunk_id) if chunk_id else None

    def plan(state: InspectionState) -> dict[str, Any]:
        """Take the next wave off the queue.

        Chunks already inspected are skipped -- chunk ids are content-derived,
        so that survives an unrelated file changing. What is left is cut at the
        first call depth boundary: chunks at one depth cannot call each other,
        which is the only reason it is safe to inspect them together.
        """
        pending = list(state.get("pending", []))
        cached = 0

        while pending and deps.store.is_inspected(pending[0]):
            pending.pop(0)
            cached += 1

        fresh: dict[str, Any] = {**clear_wave(), "stats": {"chunks_cached": cached} if cached else {}}

        if not pending:
            return {**fresh, "pending": [], "wave": [], "current": None}

        chosen = pick_wave(pending, deps.store.levels(), deps.config.wave_width, deps.subsystems)
        taken = set(chosen)
        remaining = [chunk_id for chunk_id in pending if chunk_id not in taken]

        deps.emit("wave_started", {"chunks": chosen, "remaining": len(remaining)})
        for chunk_id in chosen:
            # `file` and `symbol` for the same reason chunk_finished sends them:
            # a chunk id says nothing to a reader, and a client that only hears
            # the id cannot say which of the files on screen is being read.
            chunk = deps.store.chunk(chunk_id)
            deps.emit(
                "chunk_started",
                {
                    "chunk_id": chunk_id,
                    "file": chunk.file if chunk is not None else None,
                    "symbol": chunk.symbol if chunk is not None else None,
                    "remaining": len(remaining),
                    "total": state.get("stats", {}).get("chunks_total", 0),
                },
            )

        return {**fresh, "pending": remaining, "wave": chosen, "current": chosen[0]}

    def context(state: InspectionState) -> dict[str, Any]:
        """Assemble each chunk's context once, for everyone who will read it."""
        packs: dict[str, str] = {}
        for chunk_id in state.get("wave", []):
            chunk = deps.store.chunk(chunk_id)
            if chunk is not None:
                packs[chunk_id] = deps.pack_for(chunk).text
        return {"packs": packs}

    def triage(state: Any) -> dict[str, Any]:
        """One cheap call: is this unit worth a specialist, and whose?

        Generous by construction. A failure to answer is read as "analyse it",
        because the alternative is a chunk nobody ever looks at because a
        screening call timed out.
        """
        chunk = _chunk(state)
        if chunk is None:
            return {}

        result = deps.caller.call(
            Triage,
            deps.prompts["triage"],
            triage_user(chunk, deps.config.max_chunk_chars),
            trace=call_config(
                step="triage",
                run_id=deps.run_id,
                chunk_id=chunk.chunk_id,
                file=chunk.file,
                symbol=chunk.symbol,
                subject=chunk.symbol,
            ),
        )

        if result is None:
            log.info("triage produced nothing for %s; analysing it anyway", chunk.symbol)
            verdict = {"worth": True, "lenses": list(deps.config.lenses), "reason": "screening failed"}
            return {"triaged": {chunk.chunk_id: verdict}}

        # An empty list means "all of them", per the prompt, and the config is
        # still the ceiling: a lens that is switched off is switched off.
        picked = [lens for lens in (result.lenses or LENSES) if lens in deps.config.lenses]
        verdict = {
            "worth": bool(result.worth_analysing),
            "lenses": picked or list(deps.config.lenses),
            "reason": result.reason,
        }
        stats = {} if result.worth_analysing else {"triaged_out": 1}
        return {"triaged": {chunk.chunk_id: verdict}, "stats": stats}

    def analyst(lens: Lens) -> InspectionNode:
        """One specialist, as a node. Four of these run at once."""

        def node(state: Any) -> dict[str, Any]:
            chunk = _chunk(state)
            if chunk is None:
                return {}

            pack = deps.pack_for(chunk)
            result = deps.caller.call(
                ChunkAnalysis,
                deps.prompts[lens_prompt(lens)],
                analyse_user(pack),
                trace=call_config(
                    step=lens_prompt(lens),
                    run_id=deps.run_id,
                    chunk_id=chunk.chunk_id,
                    file=chunk.file,
                    symbol=chunk.symbol,
                    subject=chunk.symbol,
                ),
            )
            if result is None:
                log.warning("%s produced nothing usable for %s", lens, chunk.symbol)
                return {}

            # Written even with no findings: "this sanitises its input" is as
            # useful to a caller as a warning. Whichever lens has something to
            # say about the unit says it; the last one to write wins, which is
            # no worse than the single note this always was.
            if result.note.strip():
                deps.store.set_note(chunk.chunk_id, result.note.strip())

            candidates = [
                {"chunk_id": chunk.chunk_id, "lens": lens, "candidate": candidate.model_dump()}
                for candidate in result.findings
            ]
            return {
                "candidates": candidates,
                "stats": {"candidates": len(candidates)} if candidates else {},
            }

        return node

    def skip(state: Any) -> dict[str, Any]:
        """Where a screened-out chunk goes instead of to a specialist.

        It does nothing, and that is the point. Routing such a chunk straight to
        `locate` looked simpler and was wrong: `locate` would then be triggered
        by the screened-out chunk in the same super-step the specialists were
        still running in, so it ran twice for one wave -- the first time with no
        candidates at all, which closed the wave, cleared the state and started
        the next one on top of four analyses still in flight. Every chunk passes
        through this layer so the join below it fires exactly once.
        """
        return {}

    def locate(state: InspectionState) -> dict[str, Any]:
        """Merge what the specialists found, and resolve it to real spans.

        The barrier after the fan-out, and the place determinism is restored:
        four lenses finishing in whatever order they finish in are sorted back
        into one order here, so the report does not depend on which request the
        endpoint answered first.
        """
        raw = sorted(
            state.get("candidates", []),
            key=lambda item: (
                str(item.get("chunk_id")),
                str(item.get("candidate", {}).get("cwe") or ""),
                str(item.get("candidate", {}).get("anchor_text") or ""),
                str(item.get("lens")),
            ),
        )

        located: list[dict[str, Any]] = []
        seen: set[str] = set()
        dropped = 0
        per_chunk: dict[str, int] = {}

        for item in raw:
            chunk = deps.store.chunk(str(item.get("chunk_id")))
            if chunk is None:
                continue
            candidate = CandidateFinding.model_validate(item["candidate"])
            finding = _locate_candidate(candidate, chunk, deps)
            if finding is None:
                dropped += 1
                continue
            # Two lenses reporting the same expression is agreement, not two
            # findings. The id is content-derived, so this catches it.
            if finding.id in seen:
                continue
            seen.add(finding.id)

            # Verification dominates cost on a noisy chunk. Past the cap a
            # finding is kept but flagged, rather than silently dropped or
            # silently blessed.
            count = per_chunk.get(chunk.chunk_id, 0)
            per_chunk[chunk.chunk_id] = count + 1
            located.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "lens": item.get("lens"),
                    "finding": finding.model_dump(),
                    "over_cap": count >= deps.config.max_verify_per_chunk,
                }
            )

        return {"located": located, "stats": {"dropped_unlocatable": dropped} if dropped else {}}

    def verify(state: Any) -> dict[str, Any]:
        """Refute one finding. Whether it survives is decided in `reduce`."""
        chunk = _chunk(state)
        payload = state.get("finding") or {}
        if chunk is None or not payload:
            return {}

        finding = Finding.model_validate(payload)
        pack = deps.pack_for(chunk)
        # Which specialist raised this, so the trace records the hand-off.
        raised_by = state.get("lens")

        # Check the claim before ruling on it. Empty without tools.
        gathered = ""
        if deps.tools is not None:
            gathered = deps.caller.gather(
                deps.prompts["gather"],
                gather_user(finding, pack),
                deps.tools,
                deps.config.max_tool_calls,
                trace=call_config(
                    step="gather",
                    run_id=deps.run_id,
                    chunk_id=chunk.chunk_id,
                    file=chunk.file,
                    symbol=chunk.symbol,
                    subject=_finding_subject(finding),
                    lens=raised_by,
                ),
            )

        verdict = deps.caller.call(
            Verdict,
            deps.prompts["verify"],
            verify_user(finding, pack, gathered),
            trace=call_config(
                step="verify",
                run_id=deps.run_id,
                chunk_id=chunk.chunk_id,
                file=chunk.file,
                symbol=chunk.symbol,
                subject=_finding_subject(finding),
                lens=raised_by,
            ),
        )

        # No verdict is not a pass.
        refuted = verdict is None or verdict.refuted
        return {
            "verdicts": [
                {
                    "finding_id": finding.id,
                    "refuted": refuted,
                    "confidence": verdict.confidence if verdict is not None else 0.0,
                }
            ]
        }

    def reduce(state: InspectionState) -> dict[str, Any]:
        """Write down what survived, and close the wave.

        The other barrier. Everything that reaches the store or the report goes
        through here, so a wave is recorded once, in one order, whatever order
        its parts finished in.
        """
        rulings = {str(v["finding_id"]): v for v in state.get("verdicts", [])}
        by_chunk: dict[str, list[dict[str, Any]]] = {}
        refuted = 0

        for item in state.get("located", []):
            finding = Finding.model_validate(item["finding"])
            if item.get("over_cap"):
                # Never put to a verifier, so it is neither confirmed nor
                # refuted -- and says so, at a confidence that reads as one.
                finding.verified = False
                finding.confidence = 0.3
            else:
                ruling = rulings.get(finding.id)
                if ruling is None or ruling.get("refuted"):
                    refuted += 1
                    continue
                finding.verified = True
                finding.confidence = float(ruling.get("confidence", 0.0))
            by_chunk.setdefault(str(item["chunk_id"]), []).append(finding.model_dump())

        confirmed: list[dict[str, Any]] = []
        inspected = 0
        for chunk_id in state.get("wave", []):
            chunk = deps.store.chunk(chunk_id)
            if chunk is None:
                continue
            found = by_chunk.get(chunk_id, [])
            if found:
                deps.store.add_findings(chunk_id, found)
            deps.store.mark_inspected(chunk_id)
            inspected += 1
            confirmed.extend(found)
            deps.emit(
                "chunk_finished",
                {
                    "chunk_id": chunk_id,
                    "file": chunk.file,
                    "symbol": chunk.symbol,
                    "findings": found,
                    "stats": _tally(state, inspected),
                },
            )

        return {
            "confirmed": confirmed,
            "stats": {"chunks_inspected": inspected, **({"refuted": refuted} if refuted else {})},
        }

    def _tally(state: InspectionState, inspected_now: int) -> dict[str, int]:
        """The counters as the progress bar should see them mid-wave.

        The reducer has not run yet when this event is emitted, so the wave's
        own chunks have to be added by hand or the bar sits still through a
        whole wave and then jumps.
        """
        stats = dict(state.get("stats", {}))
        stats["chunks_inspected"] = stats.get("chunks_inspected", 0) + inspected_now
        return stats

    nodes: dict[str, InspectionNode] = {
        "plan": plan,
        "context": context,
        "triage": triage,
        "skip": skip,
        "locate": locate,
        "verify": verify,
        "reduce": reduce,
    }
    for lens in LENSES:
        nodes[lens] = analyst(lens)
    return nodes


# -- routers ----------------------------------------------------------------
#
# Deterministic, every one of them: the model decides what a chunk *contains*,
# never where the run goes next. That is what makes two runs over one tree
# comparable, and it is worth more here than agentic routing would be.


def has_work(state: InspectionState) -> str:
    """Loop condition: another wave, or stop."""
    return "context" if state.get("wave") else "done"


def dispatch(config: AgentConfig) -> Any:
    """From `context`: screen each chunk, or go straight to the specialists."""

    def route(state: InspectionState) -> Any:
        chunks = list(state.get("wave", []))
        if not chunks:
            return "skip"
        if config.triage:
            return [Send("triage", {"chunk_id": chunk_id}) for chunk_id in chunks]
        return [Send(lens, {"chunk_id": chunk_id}) for chunk_id in chunks for lens in config.lenses]

    return route


def specialists(state: Any) -> Any:
    """From `triage`: the lenses that chunk earned.

    Evaluated once per triage task and seeing only that task's write, so each
    chunk dispatches its own specialists and no other's.
    """
    sends: list[Send] = []
    for chunk_id, verdict in (state.get("triaged") or {}).items():
        if not verdict.get("worth"):
            continue
        for lens in verdict.get("lenses", ()):
            sends.append(Send(lens, {"chunk_id": chunk_id}))
    # A chunk screened out still passes through this layer -- see `skip`. Going
    # straight to the join from here would fire it while the specialists were
    # still running.
    return sends or [Send("skip", {})]


def claims(state: InspectionState) -> Any:
    """From `locate`: one verifier per finding worth the cost.

    Carries the lens through. `locate` knows which specialist raised each claim
    and used to drop it here, which left the trace unable to say who a verifier
    was arguing with.
    """
    sends = [
        Send(
            "verify",
            {"chunk_id": item["chunk_id"], "finding": item["finding"], "lens": item.get("lens")},
        )
        for item in state.get("located", [])
        if not item.get("over_cap")
    ]
    return sends or "reduce"


def lens_names(config: AgentConfig) -> Sequence[str]:
    """The specialist nodes a router may target, for the graph's drawing."""
    return list(config.lenses)
