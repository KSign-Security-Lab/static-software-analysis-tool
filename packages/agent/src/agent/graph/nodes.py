"""The five nodes of the inspection loop.

::

    plan -> context -> analyse -> locate -> verify -> (next chunk, or done)

``plan`` picks the next chunk and skips ones already inspected, which is what
makes re-inspection incremental. ``context`` assembles the pack from the index.
``analyse`` is one model call. ``locate`` resolves anchors to real spans and
discards what it cannot find. ``verify`` is a second model call per candidate,
prompted to refute.

The nodes are built by :func:`make_nodes` so they can close over the store, the
model client and the run root instead of carrying them in graph state.
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
    """One graph node.

    LangGraph's own node protocol requires the parameter to be *named* ``state``,
    so a plain ``Callable[[InspectionState], ...]`` -- whose parameter is
    positional-only -- does not satisfy it. Declaring the shape here keeps the
    node table assignable without a cast.
    """

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
    #: The agent's MCP client, when the tool surface came up. None means
    #: verification runs from context alone, which is a supported mode rather
    #: than a degraded one -- most claims are decidable from the context pack.
    tools: Any = None


#: A title is a chip in the UI and a marker message; a paragraph in it wraps the
#: panel and truncates the marker tooltip.
MAX_TITLE_CHARS = 120


def _clean_title(raw: str) -> str:
    """Collapse a title to one line, and bound it."""
    collapsed = " ".join(raw.split())
    if len(collapsed) <= MAX_TITLE_CHARS:
        return collapsed or "Unnamed finding"
    return collapsed[: MAX_TITLE_CHARS - 1].rstrip() + "…"


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
    """Resolve a candidate's anchors into real spans, or discard it.

    The primary anchor is mandatory: without it there is nothing to underline,
    and a marker on a guessed line is worse than no marker. Evidence anchors are
    best-effort -- losing one weakens the explanation but does not invalidate
    the finding, so the finding survives with fewer evidence items.
    """
    text = _file_text(deps.root, chunk.file)
    if text is None:
        return None

    primary = locate_anchor(candidate.anchor_text, chunk.file, text, chunk)
    if primary is None:
        # Log the anchor, not the title: the anchor is what failed and what a
        # prompt fix has to target. (This said `candidate.title` at first, which
        # made a run of degenerate empty-title output look like a locating bug.)
        log.info(
            "dropping finding in %s :: %s -- anchor not found: %r",
            chunk.file,
            chunk.symbol,
            candidate.anchor_text[:200],
        )
        return None

    evidence: list[Evidence] = []
    for item in candidate.evidence:
        # Evidence may point at another file -- that is the cross-file trail the
        # UI makes navigable -- so it is not constrained to this chunk.
        item_text = text if item.file == chunk.file else _file_text(deps.root, item.file)
        if item_text is None:
            continue
        window = chunk if item.file == chunk.file else None
        located = locate_anchor(item.anchor_text, item.file, item_text, window)
        if located is not None:
            evidence.append(Evidence(role=item.role, span=located.span, note=item.note))

    # Normalised before it reaches the id, so the same finding reported with
    # "CWE-78" one run and a prose blob the next still hashes the same.
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
        """Take the next chunk, skipping any already inspected.

        Chunk ids are content-derived, so "already inspected" survives an
        unrelated file changing -- this is what makes a re-run cheap.
        """
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
        result = deps.caller.call(ChunkAnalysis, ANALYSE_SYSTEM, analyse_user(pack))
        if result is None:
            log.warning("analyse produced nothing usable for %s", chunk.symbol)
            return {"candidates": []}

        # The note is written even when there are no findings: "this function
        # sanitises its input" is exactly as useful to a caller as a warning.
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
                # Cap reached. Keeping the finding unverified and saying so is
                # more honest than silently dropping it or silently blessing it.
                finding.verified = False
                finding.confidence = 0.3
                confirmed.append(finding.model_dump())
                continue

            if pack is None:
                pack = build_context(deps.store, chunk, deps.config)

            # Check the claim before ruling on it: read a callee, confirm the
            # input is really attacker controlled, or compile something in the
            # sandbox. Empty when tools are unavailable, which just means the
            # verdict is made from context.
            gathered = ""
            if deps.tools is not None:
                gathered = deps.caller.gather(
                    GATHER_SYSTEM,
                    gather_user(finding, pack),
                    deps.tools,
                    deps.config.max_tool_calls,
                )

            verdict = deps.caller.call(Verdict, VERIFY_SYSTEM, verify_user(finding, pack, gathered))
            if verdict is None:
                # No verdict is not a pass. Uncertainty counts against.
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
