from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Mapping, Any, Protocol, Sequence

from langgraph.types import Command, Send

from ..config import AgentConfig
from ..context import ContextPack, build_context
from ..ids import finding_id, normalize_cwe
from ..index.chunk import FILE_CHUNK_KIND, Chunk, line_windows
from ..index.order import wave as pick_wave
from ..index.reach import stamp as stamp_reach
from ..index.store import ChunkStore
from ..llm import StructuredCaller
from ..locate import locate_anchor
from ..mcp.client import LENS_TOOLS
from ..prompts import (
    analyse_user,
    gather_user,
    lookup_user,
    replan_user,
    scout_user,
    triage_user,
    verify_user,
)
from ..promptstore import DEFAULTS as DEFAULT_PROMPTS
from ..promptstore import lens_prompt
from ..remediate import build as build_remediation
from ..remediate import propose as propose_fix
from ..remediate import window_around
from ..tracing import call_config
from ..schema import (
    LENSES,
    CandidateFinding,
    ChunkAnalysis,
    Evidence,
    Finding,
    Lens,
    PlanRevision,
    Region,
    Remediation,
    Scout,
    Triage,
    Verdict,
)
from .plan import PlanEvent
from .state import InspectionState, clear_wave

log = logging.getLogger(__name__)


class ProgressSink(Protocol):
    def __call__(self, event: str, payload: dict[str, Any]) -> None: ...


class InspectionNode(Protocol):
    def __call__(self, state: InspectionState) -> dict[str, Any]: ...


def _noop(event: str, payload: dict[str, Any]) -> None:
    return None


def _plan_mark(deps: "NodeDeps", chunk_ids: Sequence[str], status: str) -> None:
    if deps.plan is None:
        return
    try:
        deps.plan.mark(chunk_ids, status)  # type: ignore[arg-type]
    except Exception:  # pragma: no cover - bookkeeping must not break a run
        log.debug("plan: could not mark %s as %s", list(chunk_ids), status, exc_info=True)


@dataclass
class NodeDeps:
    store: ChunkStore
    config: AgentConfig
    caller: StructuredCaller
    files: Mapping[str, str]
    emit: ProgressSink = _noop
    run_id: str = ""
    tools: Any = None
    prompts: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PROMPTS))
    subsystems: dict[str, int] = field(default_factory=dict)
    cache: Any = None
    plan: Any = None
    cancelled: Callable[[], bool] = lambda: False
    _packs: dict[tuple[str, tuple[int, int] | None], ContextPack] = field(default_factory=dict, repr=False)

    def pack_for(self, chunk: Chunk, region: tuple[int, int] | None = None) -> ContextPack:
        cached = self._packs.get((chunk.chunk_id, region))
        if cached is None:
            cached = build_context(self.store, chunk, self.config, region)
            self._packs[(chunk.chunk_id, region)] = cached
        return cached


MAX_TITLE_CHARS = 120


def _clean_title(raw: str) -> str:
    collapsed = " ".join(raw.split())
    if len(collapsed) <= MAX_TITLE_CHARS:
        return collapsed or "Unnamed finding"
    return collapsed[: MAX_TITLE_CHARS - 1].rstrip() + "…"


def _finding_subject(finding: Finding) -> str:
    where = f"{finding.primary.file}:{finding.primary.start_line}"
    return f"{finding.cwe} {where}" if finding.cwe else where


def _file_text(files: Mapping[str, str], relative: str) -> str | None:
    return files.get(relative)


def _locate_candidate(
    candidate: CandidateFinding,
    chunk: Chunk,
    deps: NodeDeps,
    region: tuple[int, int] | None = None,
) -> Finding | None:
    text = _file_text(deps.files, chunk.file)
    if text is None:
        return None

    primary = locate_anchor(candidate.anchor_text, chunk.file, text, chunk, region)
    if primary is None:
        log.info(
            "dropping finding in %s :: %s -- anchor not found: %r",
            chunk.file,
            chunk.symbol,
            candidate.anchor_text[:200],
        )
        return None

    evidence: list[Evidence] = []
    for item in candidate.evidence:
        item_text = text if item.file == chunk.file else _file_text(deps.files, item.file)
        if item_text is None:
            continue
        window = chunk if item.file == chunk.file else None
        located = locate_anchor(item.anchor_text, item.file, item_text, window, region if window else None)
        if located is not None:
            evidence.append(Evidence(role=item.role, span=located.span, note=item.note))

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
        remediation=build_remediation(candidate.remediation, primary.span, text),
        verified=False,
    )


def make_nodes(deps: NodeDeps) -> dict[str, InspectionNode]:
    def _chunk(state: Any) -> Chunk | None:
        chunk_id = state.get("chunk_id")
        return deps.store.chunk(chunk_id) if chunk_id else None

    def _region_of(state: Any, chunk: Chunk) -> tuple[int, int] | None:
        region = state.get("region")
        if not isinstance(region, dict):
            return None
        first, last = region.get("start_line"), region.get("end_line")
        if not isinstance(first, int) or not isinstance(last, int):
            return None
        if (first, last) == (chunk.start_line, chunk.end_line):
            return None
        return first, last

    def plan(state: InspectionState) -> dict[str, Any]:
        pending = list(state.get("pending", []))

        if deps.cancelled():
            return {**clear_wave(), "pending": pending, "wave": [], "current": None}

        if deps.config.advisory_planning and deps.plan is not None:
            still_queued = set(pending)
            revised = [chunk_id for chunk_id in deps.plan.pending() if chunk_id in still_queued]
            unplanned = [chunk_id for chunk_id in pending if chunk_id not in set(deps.plan.pending())]
            skipped = [c for c in unplanned if c not in revised]
            pending = revised
            if skipped:
                _plan_mark(deps, skipped, "skipped")

        cached = 0

        while pending and deps.store.is_inspected(pending[0]):
            popped = pending.pop(0)
            cached += 1
            _plan_mark(deps, [popped], "done")

        fresh: dict[str, Any] = {**clear_wave(), "stats": {"chunks_cached": cached} if cached else {}}

        if not pending:
            return {**fresh, "pending": [], "wave": [], "current": None}

        chosen = pick_wave(pending, deps.store.levels(), deps.config.wave_width, deps.subsystems)
        taken = set(chosen)
        remaining = [chunk_id for chunk_id in pending if chunk_id not in taken]

        deps.emit("wave_started", {"chunks": chosen, "remaining": len(remaining)})
        for chunk_id in chosen:
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

        _plan_mark(deps, chosen, "running")
        return {**fresh, "pending": remaining, "wave": chosen, "current": chosen[0]}

    def replan(state: InspectionState) -> dict[str, Any]:
        if deps.plan is None or deps.cancelled():
            return {}

        remaining = [
            (item.chunk_id, chunk.file, chunk.symbol)
            for item in deps.plan.items()
            if item.status == "pending"
            for chunk in [deps.store.chunk(item.chunk_id)]
            if chunk is not None
        ]
        if not remaining:
            return {}

        trace = call_config(step="replan", run_id=deps.run_id, subject=f"{len(remaining)} left")
        outcome = deps.caller.call(
            PlanRevision,
            deps.prompts["replan"],
            replan_user(remaining, state.get("confirmed", [])),
            trace=trace,
        )
        if not outcome.ok or outcome.value is None:
            log.info("replan produced nothing (%s); the computed order stands", outcome.reason)
            return {"stats": {"failed": 1}}

        events = [
            PlanEvent(kind=change.kind, target=change.target, reason=change.reason) for change in outcome.value.changes
        ]
        applied = deps.plan.record(events)
        if applied:
            deps.emit("plan_revised", {"events": [{"kind": e.kind, "target": e.target} for e in applied]})
        return {"stats": {"replanned": len(applied)} if applied else {}}

    def context(state: InspectionState) -> dict[str, Any]:
        packs: dict[str, str] = {}
        for chunk_id in state.get("wave", []):
            chunk = deps.store.chunk(chunk_id)
            if chunk is not None:
                packs[chunk_id] = deps.pack_for(chunk).text
        return {"packs": packs}

    def triage(state: Any) -> dict[str, Any]:
        chunk = _chunk(state)
        if chunk is None or deps.cancelled():
            return {}

        outcome = deps.caller.call(
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

        if not outcome.ok:
            log.info("triage produced nothing for %s (%s); analysing it anyway", chunk.symbol, outcome.reason)
            verdict = {
                "worth": True,
                "lenses": list(deps.config.lenses),
                "reason": f"선별 실패 ({outcome.reason})",
            }
            return {"triaged": {chunk.chunk_id: verdict}, "stats": {"failed": 1}}
        result = outcome.value
        picked = [lens for lens in (result.lenses or LENSES) if lens in deps.config.lenses]
        verdict = {
            "worth": bool(result.worth_analysing),
            "lenses": picked or list(deps.config.lenses),
            "reason": result.reason,
        }
        stats = {} if result.worth_analysing else {"triaged_out": 1}
        return {"triaged": {chunk.chunk_id: verdict}, "stats": stats}

    def _tidy(regions: Sequence[Region], chunk: Chunk) -> list[dict[str, Any]]:
        spans: list[tuple[int, int]] = []
        for region in regions:
            first = max(chunk.start_line, min(region.start_line, region.end_line))
            last = min(chunk.end_line, max(region.start_line, region.end_line))
            if first <= last:
                spans.append((first, last))
        if not spans:
            return []

        spans.sort()
        merged = [spans[0]]
        for first, last in spans[1:]:
            prior_first, prior_last = merged[-1]
            if first <= prior_last + 1:
                merged[-1] = (prior_first, max(prior_last, last))
            else:
                merged.append((first, last))
        return [{"start_line": first, "end_line": last} for first, last in merged]

    def scout(state: Any) -> dict[str, Any]:
        chunk = _chunk(state)
        if chunk is None or deps.cancelled():
            return {}

        whole = [{"start_line": chunk.start_line, "end_line": chunk.end_line}]

        if chunk.kind == FILE_CHUNK_KIND or not chunk.body_is_verbatim:
            return {"scouted": {chunk.chunk_id: whole}, "stats": {"regions": 1}}

        budget = deps.config.input_chars()
        pack = deps.pack_for(chunk)
        if not pack.truncated and not pack.dropped:
            return {"scouted": {chunk.chunk_id: whole}, "stats": {"regions": 1}}

        found: list[Region] = []
        failed = 0
        windows = line_windows(chunk, max(2_000, budget // 2))
        for first, last in windows:
            outcome = deps.caller.call(
                Scout,
                deps.prompts["scout"],
                scout_user(chunk, first, last, whole=len(windows) == 1),
                trace=call_config(
                    step="scout",
                    run_id=deps.run_id,
                    chunk_id=chunk.chunk_id,
                    file=chunk.file,
                    symbol=chunk.symbol,
                    subject=f"{chunk.symbol} {first}-{last}",
                ),
            )
            if outcome.ok:
                found.extend(outcome.value.regions)
            else:
                failed += 1

        regions = _tidy(found, chunk) or whole
        if regions == whole:
            log.info("scout found nothing to narrow in %s; reading it whole", chunk.symbol)
        stats: dict[str, int] = {"regions": len(regions)}
        if failed:
            stats["failed"] = failed
        return {"scouted": {chunk.chunk_id: regions}, "stats": stats}

    def analyst(lens: Lens) -> InspectionNode:
        def node(state: Any) -> dict[str, Any]:
            chunk = _chunk(state)
            if chunk is None or deps.cancelled():
                return {}

            region = _region_of(state, chunk)
            pack = deps.pack_for(chunk, region)
            looked_up = ""
            if deps.tools is not None and deps.config.lens_tools:
                looked_up = deps.caller.gather(
                    deps.prompts[lens_prompt(lens)],
                    lookup_user(pack),
                    deps.tools,
                    deps.config.max_lens_tool_calls,
                    allowed=LENS_TOOLS,
                    trace=call_config(
                        step=lens_prompt(lens),
                        run_id=deps.run_id,
                        chunk_id=chunk.chunk_id,
                        file=chunk.file,
                        symbol=chunk.symbol,
                        subject=f"{chunk.symbol} 조회",
                    ),
                    cancelled=deps.cancelled,
                )

            outcome = deps.caller.call(
                ChunkAnalysis,
                deps.prompts[lens_prompt(lens)],
                analyse_user(pack, looked_up),
                trace=call_config(
                    step=lens_prompt(lens),
                    run_id=deps.run_id,
                    chunk_id=chunk.chunk_id,
                    file=chunk.file,
                    symbol=chunk.symbol,
                    subject=chunk.symbol if region is None else f"{chunk.symbol} {region[0]}-{region[1]}",
                ),
            )
            if not outcome.ok:
                log.warning("%s produced nothing usable for %s (%s)", lens, chunk.symbol, outcome.reason)
                return {"stats": {"failed": 1}}
            result = outcome.value

            if result.note.strip():
                deps.store.set_note(chunk.chunk_id, result.note.strip())

            candidates = [
                {
                    "chunk_id": chunk.chunk_id,
                    "lens": lens,
                    "region": region,
                    "candidate": candidate.model_dump(),
                }
                for candidate in result.findings
            ]
            return {
                "candidates": candidates,
                "stats": {"candidates": len(candidates)} if candidates else {},
            }

        return node

    def skip(state: Any) -> dict[str, Any]:
        return {}

    def locate(state: InspectionState) -> dict[str, Any]:
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
            raw = item.get("region")
            region = (int(raw[0]), int(raw[1])) if isinstance(raw, (list, tuple)) and len(raw) == 2 else None
            finding = _locate_candidate(candidate, chunk, deps, region)
            if finding is None:
                dropped += 1
                continue
            if finding.id in seen:
                continue
            seen.add(finding.id)

            count = per_chunk.get(chunk.chunk_id, 0)
            per_chunk[chunk.chunk_id] = count + 1
            raised_by = item.get("lens")
            if raised_by in LENSES:
                finding.lens = raised_by
            located.append(
                {
                    "chunk_id": chunk.chunk_id,
                    "lens": item.get("lens"),
                    "finding": finding.model_dump(),
                    "over_cap": count >= deps.config.max_verify_per_chunk,
                }
            )

        return {"located": located, "stats": {"dropped_unlocatable": dropped} if dropped else {}}

    def gather(state: Any) -> Any:
        chunk = _chunk(state)
        payload = state.get("finding") or {}
        if chunk is None or not payload:
            return Command(goto=[])

        finding = Finding.model_validate(payload)
        raised_by = state.get("lens")
        gathered = ""
        if deps.tools is not None and not deps.cancelled():
            gathered = deps.caller.gather(
                deps.prompts["gather"],
                gather_user(finding, deps.pack_for(chunk)),
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
                cancelled=deps.cancelled,
            )

        return Command(
            goto=[
                Send(
                    "verify",
                    {
                        "chunk_id": state.get("chunk_id"),
                        "finding": payload,
                        "lens": raised_by,
                        "gathered": gathered,
                    },
                )
            ]
        )

    def verify(state: Any) -> dict[str, Any]:
        chunk = _chunk(state)
        payload = state.get("finding") or {}
        if chunk is None or not payload:
            return {}

        finding = Finding.model_validate(payload)

        if deps.cancelled():
            return {
                "verdicts": [
                    {
                        "finding_id": finding.id,
                        "refuted": False,
                        "verified": False,
                        "confidence": 0.0,
                    }
                ]
            }

        pack = deps.pack_for(chunk)
        raised_by = state.get("lens")
        gathered = state.get("gathered") or ""
        outcome = deps.caller.call(
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

        verdict = outcome.value
        refuted = verdict.refuted if verdict is not None else False
        return {
            "verdicts": [
                {
                    "finding_id": finding.id,
                    "refuted": refuted,
                    "verified": verdict is not None,
                    "confidence": verdict.confidence if verdict is not None else 0.0,
                    **({"remediation": _fix(finding, chunk, raised_by)} if verdict is not None and not refuted else {}),
                }
            ],
            **({} if verdict is not None else {"stats": {"failed": 1}}),
        }

    def _fix(finding: Finding, chunk: Chunk, raised_by: str | None) -> dict[str, Any] | None:
        if (finding.remediation.replacement or "").strip():
            return None
        if deps.cancelled():
            return None
        text = _file_text(deps.files, finding.primary.file)
        if text is None:
            return None

        lines = text.splitlines()
        span = finding.primary
        if span.start_line < 1 or span.end_line > len(lines):
            return None

        candidate = propose_fix(
            deps.caller,
            title=finding.title,
            explanation=finding.explanation,
            span=span,
            excerpt="\n".join(lines[span.start_line - 1 : span.end_line]),
            context=window_around(text, span, deps.config.input_chars()),
            prompt=deps.prompts["fix"],
            trace=call_config(
                step="fix",
                run_id=deps.run_id,
                chunk_id=chunk.chunk_id,
                file=chunk.file,
                symbol=chunk.symbol,
                subject=_finding_subject(finding),
                lens=raised_by,
            ),
        )
        if not candidate.ok:
            return None
        built = build_remediation(candidate.value, span, text)
        return built.model_dump() if built.replacement else None

    def reduce(state: InspectionState) -> dict[str, Any]:
        rulings = {str(v["finding_id"]): v for v in state.get("verdicts", [])}
        by_chunk: dict[str, list[dict[str, Any]]] = {}
        refuted = 0

        for item in state.get("located", []):
            finding = Finding.model_validate(item["finding"])
            if item.get("over_cap"):
                finding.verified = False
                finding.confidence = 0.3
            else:
                ruling = rulings.get(finding.id)
                if ruling is None or ruling.get("refuted"):
                    refuted += 1
                    continue
                if not ruling.get("verified", True):
                    finding.verified = False
                    finding.confidence = 0.3
                    by_chunk.setdefault(str(item["chunk_id"]), []).append(finding.model_dump())
                    continue
                finding.verified = True
                finding.confidence = float(ruling.get("confidence", 0.0))
                fixed = ruling.get("remediation")
                if fixed:
                    finding.remediation = Remediation.model_validate(fixed)
            by_chunk.setdefault(str(item["chunk_id"]), []).append(finding.model_dump())

        _plan_mark(deps, state.get("wave", []), "done")

        confirmed: list[dict[str, Any]] = []
        inspected = 0
        reach = deps.store.reach()
        for chunk_id in state.get("wave", []):
            chunk = deps.store.chunk(chunk_id)
            if chunk is None:
                continue
            found = by_chunk.get(chunk_id, [])
            if found:
                deps.store.add_findings(chunk_id, found)
            deps.store.mark_inspected(chunk_id)
            if deps.cache is not None:
                deps.cache.remember(chunk_id, found, deps.store.note(chunk_id) or "")
            inspected += 1
            confirmed.extend(found)
            deps.emit(
                "chunk_finished",
                {
                    "chunk_id": chunk_id,
                    "file": chunk.file,
                    "symbol": chunk.symbol,
                    "findings": stamp_reach(found, reach),
                    "stats": _tally(state, inspected),
                },
            )

        return {
            "confirmed": confirmed,
            "stats": {"chunks_inspected": inspected, **({"refuted": refuted} if refuted else {})},
        }

    def _tally(state: InspectionState, inspected_now: int) -> dict[str, int]:
        stats = dict(state.get("stats", {}))
        stats["chunks_inspected"] = stats.get("chunks_inspected", 0) + inspected_now
        return stats

    nodes: dict[str, InspectionNode] = {
        "plan": plan,
        "replan": replan,
        "context": context,
        "triage": triage,
        "scout": scout,
        "skip": skip,
        "locate": locate,
        "gather": gather,
        "verify": verify,
        "reduce": reduce,
    }
    for lens in LENSES:
        nodes[lens] = analyst(lens)
    return nodes


def has_work(state: InspectionState) -> str:
    return "context" if state.get("wave") else "done"


def dispatch(config: AgentConfig) -> Any:
    def route(state: InspectionState) -> Any:
        chunks = list(state.get("wave", []))
        if not chunks:
            return "skip"
        if config.triage:
            return [Send("triage", {"chunk_id": chunk_id}) for chunk_id in chunks]
        return [Send("scout", {"chunk_id": chunk_id}) for chunk_id in chunks]

    return route


def scouts(state: Any) -> Any:
    sends = [
        Send("scout", {"chunk_id": chunk_id})
        for chunk_id, verdict in (state.get("triaged") or {}).items()
        if verdict.get("worth")
    ]
    return sends or [Send("scout", {})]


def specialists(config: AgentConfig) -> Any:
    def route(state: Any) -> Any:
        sends: list[Send] = []
        triaged = state.get("triaged") or {}
        for chunk_id, regions in (state.get("scouted") or {}).items():
            verdict = triaged.get(chunk_id, {})
            if triaged and not verdict.get("worth", False):
                continue
            picked = [lens for lens in (verdict.get("lenses") or config.lenses) if lens in config.lenses]
            for region in regions:
                for lens in picked or config.lenses:
                    sends.append(Send(lens, {"chunk_id": chunk_id, "region": region}))
        return sends or [Send("skip", {})]

    return route


def claims(state: InspectionState) -> Any:
    sends = [
        Send(
            "gather",
            {"chunk_id": item["chunk_id"], "finding": item["finding"], "lens": item.get("lens")},
        )
        for item in state.get("located", [])
        if not item.get("over_cap")
    ]
    return sends or "reduce"


def lens_names(config: AgentConfig) -> Sequence[str]:
    return list(config.lenses)
