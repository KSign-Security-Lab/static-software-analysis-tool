"""The five nodes of the inspection loop.

    plan -> context -> analyse -> locate -> verify -> (next chunk, or done)

Built by :func:`make_nodes` so they close over the store, the model client and
the run root instead of carrying them in graph state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..config import AgentConfig
from ..context import ContextPack, build_context
from ..ids import finding_id, normalize_cwe
from ..index.chunk import Chunk
from ..index.store import ChunkStore
from ..llm import StructuredCaller
from ..locate import locate_anchor
from ..prompts import (
    ANALYSE_SYSTEM,
    GATHER_SYSTEM,
    VERIFY_SYSTEM,
    analyse_user,
    gather_user,
    verify_user,
)
from ..tracing import call_config
from ..schema import (
    CandidateFinding,
    ChunkAnalysis,
    Evidence,
    Finding,
    Remediation,
    Verdict,
)
from .state import InspectionState

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

    def plan(state: InspectionState) -> dict[str, Any]:
        """Next chunk, skipping any already inspected. Chunk ids are
        content-derived, so that survives an unrelated file changing."""
        pending = list(state.get("pending", []))
        stats = dict(state.get("stats", {}))

        while pending:
            chunk_id = pending.pop(0)
            if deps.store.is_inspected(chunk_id):
                stats["chunks_cached"] = stats.get("chunks_cached", 0) + 1
                continue
            deps.emit(
                "chunk_started",
                {"chunk_id": chunk_id, "remaining": len(pending), "total": stats.get("chunks_total", 0)},
            )
            return {"pending": pending, "current": chunk_id, "stats": stats, "confirmed": []}

        return {"pending": [], "current": None, "stats": stats, "confirmed": []}

    def context(state: InspectionState) -> dict[str, Any]:
        chunk_id = state.get("current")
        if not chunk_id:
            return {}
        chunk = deps.store.chunk(chunk_id)
        if chunk is None:
            return {"context_text": ""}
        pack = build_context(deps.store, chunk, deps.config)
        return {"context_text": pack.text}

    def analyse(state: InspectionState) -> dict[str, Any]:
        """One model call for the current chunk."""
        chunk_id = state.get("current")
        chunk = deps.store.chunk(chunk_id) if chunk_id else None
        if chunk is None:
            return {"candidates": []}

        pack = build_context(deps.store, chunk, deps.config)
        result = deps.caller.call(
            ChunkAnalysis,
            ANALYSE_SYSTEM,
            analyse_user(pack),
            trace=call_config(
                step="analyse",
                run_id=deps.run_id,
                chunk_id=chunk.chunk_id,
                file=chunk.file,
                symbol=chunk.symbol,
                subject=chunk.symbol,
            ),
        )
        if result is None:
            log.warning("analyse produced nothing usable for %s", chunk.symbol)
            return {"candidates": []}

        # Written even with no findings: "this sanitises its input" is as
        # useful to a caller as a warning.
        if result.note.strip():
            deps.store.set_note(chunk.chunk_id, result.note.strip())

        stats = dict(state.get("stats", {}))
        stats["candidates"] = stats.get("candidates", 0) + len(result.findings)
        return {
            "candidates": [candidate.model_dump() for candidate in result.findings],
            "stats": stats,
        }

    def locate(state: InspectionState) -> dict[str, Any]:
        """Resolve anchors to spans. Unlocatable findings are dropped."""
        chunk_id = state.get("current")
        chunk = deps.store.chunk(chunk_id) if chunk_id else None
        if chunk is None:
            return {"located": []}

        stats = dict(state.get("stats", {}))
        located: list[dict[str, Any]] = []
        for raw in state.get("candidates", []):
            candidate = CandidateFinding.model_validate(raw)
            finding = _locate_candidate(candidate, chunk, deps)
            if finding is None:
                stats["dropped_unlocatable"] = stats.get("dropped_unlocatable", 0) + 1
                continue
            located.append(finding.model_dump())

        return {"located": located, "stats": stats}

    def verify(state: InspectionState) -> dict[str, Any]:
        """Refute each located finding; keep only what survives."""
        chunk_id = state.get("current")
        chunk = deps.store.chunk(chunk_id) if chunk_id else None
        if chunk is None:
            return {"confirmed": []}

        located = state.get("located", [])
        stats = dict(state.get("stats", {}))
        confirmed: list[dict[str, Any]] = []

        pack: ContextPack | None = None
        for index, raw in enumerate(located):
            finding = Finding.model_validate(raw)

            if index >= deps.config.max_verify_per_chunk:
                # Cap reached: kept but flagged, rather than silently dropped
                # or silently blessed.
                finding.verified = False
                finding.confidence = 0.3
                confirmed.append(finding.model_dump())
                continue

            if pack is None:
                pack = build_context(deps.store, chunk, deps.config)

            # Check the claim before ruling on it. Empty without tools.
            gathered = ""
            if deps.tools is not None:
                gathered = deps.caller.gather(
                    GATHER_SYSTEM,
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
                    ),
                )

            verdict = deps.caller.call(
                Verdict,
                VERIFY_SYSTEM,
                verify_user(finding, pack, gathered),
                trace=call_config(
                    step="verify",
                    run_id=deps.run_id,
                    chunk_id=chunk.chunk_id,
                    file=chunk.file,
                    symbol=chunk.symbol,
                    subject=_finding_subject(finding),
                ),
            )
            if verdict is None:
                # No verdict is not a pass.
                stats["refuted"] = stats.get("refuted", 0) + 1
                continue
            if verdict.refuted:
                stats["refuted"] = stats.get("refuted", 0) + 1
                continue

            finding.verified = True
            finding.confidence = verdict.confidence
            confirmed.append(finding.model_dump())

        if confirmed:
            deps.store.add_findings(chunk.chunk_id, confirmed)
        deps.store.mark_inspected(chunk.chunk_id)

        stats["chunks_inspected"] = stats.get("chunks_inspected", 0) + 1
        deps.emit(
            "chunk_finished",
            {
                "chunk_id": chunk.chunk_id,
                "file": chunk.file,
                "symbol": chunk.symbol,
                "findings": confirmed,
                "stats": stats,
            },
        )
        return {"confirmed": confirmed, "stats": stats}

    return {"plan": plan, "context": context, "analyse": analyse, "locate": locate, "verify": verify}


def has_work(state: InspectionState) -> str:
    """Loop condition: another chunk, or stop."""
    return "context" if state.get("current") else "done"
