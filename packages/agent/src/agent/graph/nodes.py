"""The nodes of the inspection loop, and the routers that fan them out.

    plan -> context -> triage -> scout -> {memory, injection, access, logic}
         -> locate -> gather -> verify -> reduce -> (next wave, or done)

Three things happen at once here, and each is a different kind of parallelism.
A *wave* is several chunks at one call depth, which by construction cannot need
each other's notes. A *scout* is one unit being read for where in it is worth a
close look, and a *lens* is one of the specialists reading one of those
stretches for its own family of defect. A *gather* and the *verify* below it are one claim
being investigated and then refuted. All of them fan out through LangGraph's
`Send`, so the graph shows what is actually in flight rather than one node that
takes a long time.

`gather` fans out to `verify` itself rather than reaching it by a plain edge,
and that is load-bearing. The claim under investigation travels in the `Send`
payload, not in graph state -- `finding`, `lens` and `chunk_id` are not channels
-- so an ordinary edge would turn `verify` into a join that fires once per
super-step with no claim in front of it, return nothing, and let `reduce` count
every finding as refuted. Silently.

A *missing* ruling still counts as refuted, because it means the verifier was
never reached. A ruling that says its call *failed* does not: that claim was put
to a verifier and the verifier broke, which is not a judgement about the claim.

Built by :func:`make_nodes` so they close over the store, the model client and
the run root instead of carrying them in graph state.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Mapping, Any, Protocol, Sequence

from langgraph.types import Command, Send

from ..config import AgentConfig
from ..context import ContextPack, build_context
from ..ids import finding_id, normalize_cwe
from ..index.chunk import FILE_CHUNK_KIND, Chunk, line_windows
from ..index.order import wave as pick_wave
from ..index.store import ChunkStore
from ..llm import StructuredCaller
from ..locate import locate_anchor
from ..mcp.client import LENS_TOOLS
from ..prompts import analyse_user, gather_user, lookup_user, scout_user, triage_user, verify_user
from ..promptstore import DEFAULTS as DEFAULT_PROMPTS
from ..promptstore import lens_prompt
from ..remediate import build as build_remediation
from ..remediate import propose as propose_fix
from ..tracing import call_config
from ..schema import (
    LENSES,
    CandidateFinding,
    ChunkAnalysis,
    Evidence,
    Finding,
    Lens,
    Region,
    Remediation,
    Scout,
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
    files: Mapping[str, str]
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
    # Results from earlier runs over the same code, when one is open. None means
    # every unit is analysed afresh, which is what `force` asks for.
    cache: Any = None
    # One assembled pack per chunk, for this run. Four specialists and a
    # verifier all want the same one; building it is deterministic and cheap,
    # but not free, and doing it five times says something untrue about the
    # cost of a lens.
    #
    # Keyed by chunk *and* region: one unit read whole and the same unit read in
    # two stretches are three different packs, and a key of chunk id alone would
    # hand the second region the first one's.
    _packs: dict[tuple[str, tuple[int, int] | None], ContextPack] = field(default_factory=dict, repr=False)

    def pack_for(self, chunk: Chunk, region: tuple[int, int] | None = None) -> ContextPack:
        cached = self._packs.get((chunk.chunk_id, region))
        if cached is None:
            cached = build_context(self.store, chunk, self.config, region)
            self._packs[(chunk.chunk_id, region)] = cached
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


def _file_text(files: Mapping[str, str], relative: str) -> str | None:
    """One of the run's files, or None.

    Was a read off disk under the run root. The tree is a mapping now, so a
    missing file is a missing key -- and there is no `OSError` to swallow.
    """
    return files.get(relative)


def _locate_candidate(
    candidate: CandidateFinding,
    chunk: Chunk,
    deps: NodeDeps,
    region: tuple[int, int] | None = None,
) -> Finding | None:
    """Resolve a candidate's anchors, or discard it.

    The primary anchor is mandatory. Evidence anchors are best-effort: losing
    one weakens the explanation but does not invalidate the finding.

    ``region`` is the stretch the specialist was shown. Without it a quote that
    appears twice in the unit resolves to the first one -- which may be in the
    half this specialist never read.
    """
    text = _file_text(deps.files, chunk.file)
    if text is None:
        return None

    primary = locate_anchor(candidate.anchor_text, chunk.file, text, chunk, region)
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
        item_text = text if item.file == chunk.file else _file_text(deps.files, item.file)
        if item_text is None:
            continue
        window = chunk if item.file == chunk.file else None
        located = locate_anchor(item.anchor_text, item.file, item_text, window, region if window else None)
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
        remediation=build_remediation(candidate.remediation, primary.span, text),
        verified=False,
    )


def make_nodes(deps: NodeDeps) -> dict[str, InspectionNode]:
    """Build the node functions, bound to one run's dependencies."""

    def _chunk(state: Any) -> Chunk | None:
        chunk_id = state.get("chunk_id")
        return deps.store.chunk(chunk_id) if chunk_id else None

    def _region_of(state: Any, chunk: Chunk) -> tuple[int, int] | None:
        """The stretch this task was pointed at, or None for the whole unit.

        None rather than the unit's own bounds, so everything downstream can
        tell "read it all" from "read exactly this" -- the pack cache keys on it
        and a whole-unit read must not get a second entry of its own.
        """
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
            # Fail-open and counted. Analysing a unit the screen could not judge
            # is the safe direction, but it is still a call that did not happen.
            return {"triaged": {chunk.chunk_id: verdict}, "stats": {"failed": 1}}
        result = outcome.value

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

    def _tidy(regions: Sequence[Region], chunk: Chunk) -> list[dict[str, Any]]:
        """Model answers into ranges that can be trusted downstream.

        Clamped, ordered and merged. The numbers came from a model, so a range
        that reaches past the unit, runs backwards, or overlaps its neighbour is
        an ordinary answer rather than an exception -- and every one of those
        would reach `locate`, where a wrong window puts a finding on a line
        nobody read.
        """
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
            # Touching counts as overlapping: two adjacent ranges are one read,
            # and splitting them would ask a specialist the same question twice.
            if first <= prior_last + 1:
                merged[-1] = (prior_first, max(prior_last, last))
            else:
                merged.append((first, last))
        return [{"start_line": first, "end_line": last} for first, last in merged]

    def scout(state: Any) -> dict[str, Any]:
        """Where in this unit is worth a specialist's close attention.

        The mirror of `triage` one level down. Triage prunes units; this prunes
        the parts of a unit, so an oversized function stops being all-or-nothing
        and a specialist reads a stretch it can afford to read properly.

        Costs nothing on the ordinary unit. If the pack already fits the window
        there is nothing to narrow, so the whole unit is the one region and no
        model is called -- the node still exists, because the drawing of the
        agent should not change shape with the size of the input.

        Generous by construction, like triage: no answer, or an answer with
        nothing in it, means read the whole unit. A unit nobody looks at because
        a screening call came back empty is the one outcome worth avoiding.
        """
        chunk = _chunk(state)
        if chunk is None:
            return {}

        whole = [{"start_line": chunk.start_line, "end_line": chunk.end_line}]

        # A file chunk's body is a synthesized concatenation with definitions
        # elided, so its line numbers do not map onto disk and a range against
        # them would point at nothing. Its declarations are short anyway.
        if chunk.kind == FILE_CHUNK_KIND or not chunk.body_is_verbatim:
            return {"scouted": {chunk.chunk_id: whole}, "stats": {"regions": 1}}

        budget = deps.config.input_chars()
        pack = deps.pack_for(chunk)
        # `truncated` first, and it is the one that matters: `build_context`
        # cuts the code under analysis at `max_chunk_chars` before anything here
        # sees it, so measuring the pack alone would find an oversized unit
        # already shortened and pronounce it small enough. That is the silent
        # cut this whole pass exists to replace, hiding inside the test for it.
        if not pack.truncated and len(pack.text) <= budget:
            return {"scouted": {chunk.chunk_id: whole}, "stats": {"regions": 1}}

        found: list[Region] = []
        failed = 0
        # Half the budget, because a window is only the code: the pack built
        # around each region still has to fit its callee notes, type definitions
        # and callers into the same window afterwards.
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
                # Reading the whole unit instead of a narrowed window is safe --
                # it costs tokens, not coverage -- but it is still a lost call.
                failed += 1

        regions = _tidy(found, chunk) or whole
        if regions == whole:
            log.info("scout found nothing to narrow in %s; reading it whole", chunk.symbol)
        stats: dict[str, int] = {"regions": len(regions)}
        if failed:
            stats["failed"] = failed
        return {"scouted": {chunk.chunk_id: regions}, "stats": stats}

    def analyst(lens: Lens) -> InspectionNode:
        """One specialist, as a node. Four of these run at once."""

        def node(state: Any) -> dict[str, Any]:
            chunk = _chunk(state)
            if chunk is None:
                return {}

            region = _region_of(state, chunk)
            pack = deps.pack_for(chunk, region)

            # Look things up before reading, if this deployment allows it. The
            # specialists had no tools for a reason that did not survive
            # examination: reproducibility, argued before triage and scout put a
            # model in the funnel, and then that models ignore tools -- which
            # this project's own traces contradict. Only deterministic lookups,
            # so what a lens sees still does not depend on where it wandered.
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
                # The unit was NOT analysed by this lens. It used to return an
                # empty dict here, which is indistinguishable from "looked and
                # found nothing" -- and that is how a real buffer overflow was
                # lost: `memory` died on the token limit while `injection`
                # succeeded, so the unit looked fully read and was not.
                log.warning("%s produced nothing usable for %s (%s)", lens, chunk.symbol, outcome.reason)
                return {"stats": {"failed": 1}}
            result = outcome.value

            # Written even with no findings: "this sanitises its input" is as
            # useful to a caller as a warning. Whichever lens has something to
            # say about the unit says it; the last one to write wins, which is
            # no worse than the single note this always was.
            if result.note.strip():
                deps.store.set_note(chunk.chunk_id, result.note.strip())

            candidates = [
                {
                    "chunk_id": chunk.chunk_id,
                    "lens": lens,
                    # Carried so `locate` resolves the anchor inside what this
                    # specialist actually read, not the first match in the unit.
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
            # A pair, and a list once it has been through a checkpoint: state is
            # JSON on disk, and a tuple does not survive the round trip as one.
            raw = item.get("region")
            region = (int(raw[0]), int(raw[1])) if isinstance(raw, (list, tuple)) and len(raw) == 2 else None
            finding = _locate_candidate(candidate, chunk, deps, region)
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

    def gather(state: Any) -> Any:
        """Look things up before ruling on one claim.

        Its own node rather than the first half of `verify`, because this is
        where the agent goes and reads things -- and "where did it go looking"
        should be somewhere you can stop the run and stand. It is the only step
        holding tools, so it is also the only one whose cost is unbounded by the
        prompt.

        Runs whether or not tools are configured; without them it forwards an
        empty transcript. The drawing of the agent should not change shape with
        the deployment, which is the same rule `build.NODES` applies to a lens
        that this run happens not to use.

        Hands the claim on itself, in the `Send` -- see the module docstring for
        why an edge here would quietly empty the report.
        """
        chunk = _chunk(state)
        payload = state.get("finding") or {}
        if chunk is None or not payload:
            # Nothing to investigate and nothing to rule on. `reduce` reads a
            # missing verdict as refuted, which is what it did before this node
            # existed and `verify` returned empty.
            return Command(goto=[])

        finding = Finding.model_validate(payload)
        # Which specialist raised this, so the trace records the hand-off.
        raised_by = state.get("lens")

        gathered = ""
        if deps.tools is not None:
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
                    # Also what keeps this call's span from being named after
                    # the node and read as a second node span.
                    subject=_finding_subject(finding),
                    lens=raised_by,
                ),
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
        """Refute one finding. Whether it survives is decided in `reduce`."""
        chunk = _chunk(state)
        payload = state.get("finding") or {}
        if chunk is None or not payload:
            return {}

        finding = Finding.model_validate(payload)
        pack = deps.pack_for(chunk)
        raised_by = state.get("lens")
        # Whatever `gather` turned up, carried in the Send rather than through a
        # state channel: a tool transcript is bulky and a channel would put a
        # copy of it in every checkpoint from here to the end of the run.
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
        # A call that died is not a refutation.
        #
        # This used to read `verdict is None or verdict.refuted`, so a timeout or
        # a token-limit failure was recorded as a considered negative judgement
        # and the finding was dropped from the report. That is not a missing
        # answer, it is a wrong one -- and it is the only place in the pipeline
        # that could delete a real bug on a transport error.
        #
        # Unverified now, which `standingOf` on the web already renders as
        # 취약 후보 rather than 취약 확인: a candidate the run could not rule on.
        refuted = verdict.refuted if verdict is not None else False
        return {
            "verdicts": [
                {
                    "finding_id": finding.id,
                    "refuted": refuted,
                    "verified": verdict is not None,
                    "confidence": verdict.confidence if verdict is not None else 0.0,
                    # Not for a claim nobody ruled on: a fix for an unverified
                    # candidate is model time spent on a maybe.
                    **({"remediation": _fix(finding, chunk, raised_by)} if verdict is not None and not refuted else {}),
                }
            ],
            **({} if verdict is not None else {"stats": {"failed": 1}}),
        }

    def _fix(finding: Finding, chunk: Chunk, raised_by: str | None) -> dict[str, Any] | None:
        """Code for a finding that survived, made here rather than on a button.

        A specialist proposes a fix while it is analysing, and only when one
        happens to fit the lines its anchor resolved to. When it does not, the
        reader used to be offered a button that spent thirty seconds of model time
        while they watched it say 만드는 중 -- work the run was already positioned
        to do, on a claim it had just finished proving, with the file in hand.

        Here, because this is where a claim is known to have survived: refuted
        findings never reach the report, and fixing them would be most of the
        calls spent on findings nobody will read.

        Failure is silence. A fix is the one part of a finding that is optional --
        the report is worth having without it -- so nothing here may cost the run
        a finding it has already proved.
        """
        if (finding.remediation.replacement or "").strip():
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
            context=text,
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
            # Silence in the report, but the trace has the span with its error
            # on it -- which is what lets the surface say `고칠 코드 생성 실패`
            # rather than offering to generate a fix that has already failed.
            return None
        built = build_remediation(candidate.value, span, text)
        return built.model_dump() if built.replacement else None

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
                if not ruling.get("verified", True):
                    # The verifier was reached and its call died. Same standing
                    # as `over_cap` above -- never actually ruled on, so neither
                    # confirmed nor refuted, at a confidence that reads as one.
                    # It survives into the report as a candidate rather than
                    # being deleted, which is what a failed call used to do.
                    finding.verified = False
                    finding.confidence = 0.3
                    by_chunk.setdefault(str(item["chunk_id"]), []).append(finding.model_dump())
                    continue
                finding.verified = True
                finding.confidence = float(ruling.get("confidence", 0.0))
                # Made in `verify`, applied here, because this is where the
                # finding that reaches the report is assembled.
                fixed = ruling.get("remediation")
                if fixed:
                    finding.remediation = Remediation.model_validate(fixed)
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
            # Remembered for the next run over this code. A clean unit is a
            # result too: establishing it cost the same and is worth the same.
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
        return [Send("scout", {"chunk_id": chunk_id}) for chunk_id in chunks]

    return route


def scouts(state: Any) -> Any:
    """From `triage`: one narrowing pass per unit worth analysing.

    A screened-out unit goes to `scout` too, with nothing to scout, and that is
    load-bearing rather than tidy. Every route from here has to reach `locate`
    in the same number of super-steps, and the analysis path is now three --
    scout, then a specialist, then the join. Sending a screened-out unit
    straight to `skip` makes it two, so `skip` reaches the join a whole
    super-step before the specialists write, and `locate` runs on an empty
    `candidates`: the wave closes early and everything the specialists found is
    thrown away. Silently, and only when a wave holds both kinds of unit.

    That is the bug `skip` was introduced for, one layer down. Inserting a node
    between the fan-out and the join brings it straight back unless every branch
    is lengthened with it.
    """
    sends = [
        Send("scout", {"chunk_id": chunk_id})
        for chunk_id, verdict in (state.get("triaged") or {}).items()
        if verdict.get("worth")
    ]
    # An empty task: `scout` finds no chunk, writes nothing, and `specialists`
    # below turns that into the `skip` that keeps the layer full.
    return sends or [Send("scout", {})]


def specialists(config: AgentConfig) -> Any:
    """From `scout`: every lens that chunk earned, over every region it holds.

    A closure over the config for the same reason `dispatch` is one: with
    screening off there is no verdict to read the lenses from, and the
    configuration is still the ceiling. Falling back to all four here is how a
    run asked for one specialist quietly gets four.
    """

    def route(state: Any) -> Any:
        sends: list[Send] = []
        triaged = state.get("triaged") or {}
        for chunk_id, regions in (state.get("scouted") or {}).items():
            verdict = triaged.get(chunk_id, {})
            # No verdict means screening is off and `dispatch` sent this chunk
            # here directly, which is a reason to analyse rather than to skip.
            if triaged and not verdict.get("worth", False):
                continue
            picked = [lens for lens in (verdict.get("lenses") or config.lenses) if lens in config.lenses]
            for region in regions:
                for lens in picked or config.lenses:
                    sends.append(Send(lens, {"chunk_id": chunk_id, "region": region}))
        # Evaluated once per scout task, so a unit with nothing to scout -- one
        # screened out, or one whose id did not resolve -- lands here with an
        # empty write and keeps the layer full. See `scouts` for why that
        # matters more than it looks.
        return sends or [Send("skip", {})]

    return route


def claims(state: InspectionState) -> Any:
    """From `locate`: one investigation per finding worth the cost.

    Carries the lens through. `locate` knows which specialist raised each claim
    and used to drop it here, which left the trace unable to say who a verifier
    was arguing with.
    """
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
    """The specialist nodes a router may target, for the graph's drawing."""
    return list(config.lenses)
