"""Starting, resuming, streaming and reporting an inspection.

An inspection takes minutes, so it does not happen inside the request that
starts it: the work goes to a thread, progress is streamed over SSE, and the
finished report is fetched separately.
"""

from __future__ import annotations

import queue
from dataclasses import field
from agent.graph.build import NODES

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.config import AgentConfig
from agent.graph.session import InspectionSession, ParallelStep
from agent.runs import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_INSPECTING,
    STATUS_INTERRUPTED,
    Run,
)
from agent.schema import Report

from .channels import (
    INTERRUPT_TIMEOUT_SECONDS,
    SSE_KEEPALIVE_SECONDS,
    SSE_POLL_SECONDS,
    RunChannel,
    _channel,
    _live_channel,
)
from .deps import RunDep

log = logging.getLogger(__name__)
router = APIRouter()


class InspectRequest(BaseModel):
    """Options for starting an inspection."""

    #: Re-inspect chunks that already have results. Off by default, because the
    #: whole point of content-derived chunk ids is that unchanged code is free.
    force: bool = False
    #: Nodes to stop *before*, so the state can be read and changed on the way
    #: past. Validated against the graph, since a misspelled node would
    #: otherwise be a breakpoint that silently never fires.
    breakpoints: List[str] = []
    #: Nodes to stop *after*, once they have written.
    breakpoints_after: List[str] = []
    #: Overrides on the starting state -- a shorter queue to try one chunk, say.
    #: Merged over the computed one rather than replacing it.
    values: Optional[Dict[str, Any]] = None


class ResumeRequest(BaseModel):
    """What to do with a run that stopped at a breakpoint."""

    #: ``resume`` carries on, ``abort`` gives up and reports what it has.
    action: str = "resume"
    #: Written over the state before carrying on. Editing the state is the
    #: reason to stop at all.
    values: Optional[Dict[str, Any]] = None
    #: Carry on from an earlier point instead of the latest one, which branches
    #: the run there rather than continuing the line it was on.
    checkpoint_id: Optional[str] = None
    #: Where the new worker should stop. Only read when there is no worker left
    #: to steer -- a live one already has the breakpoints it was started with.
    breakpoints: List[str] = []
    breakpoints_after: List[str] = []


@dataclass
class WorkOrder:
    """What a worker thread has been asked to do."""

    #: Nodes to stop before, and to stop after.
    breakpoints: List[str] = field(default_factory=list)
    breakpoints_after: List[str] = field(default_factory=list)
    #: Throw away cached results and inspect every chunk again.
    force: bool = False
    #: Overrides on the starting state, from the studio's input pane.
    values: Optional[Dict[str, Any]] = None
    #: Carry on from an existing history instead of starting over. The trace and
    #: the checkpoints are left alone in this case -- clearing them is what a
    #: fresh start means, and it would delete the very history being resumed.
    resume_from: Optional[str] = None
    resume_values: Optional[Dict[str, Any]] = None
    #: Whether this is a fresh start. Held rather than derived, because a resume
    #: with nothing to write looks exactly like a start that was given nothing.
    resuming: bool = False

    @property
    def fresh(self) -> bool:
        return not self.resuming


def _inspect_worker(run: Run, channel: RunChannel, order: WorkOrder) -> None:
    """Drive one inspection on a worker thread, publishing progress.

    The loop exists for breakpoints: the graph returns when it stops at one, and
    the run is not over -- it is waiting. The session stays open across the wait
    so the MCP subprocess and the chunk store are still there when it carries on.
    """
    config = AgentConfig()
    store = run.store()
    if order.fresh:
        # Two attempts interleaved in one history read as one incoherent run.
        run.reset_debug()
    spans = run.spans()

    def emit(event: str, payload: dict[str, Any]) -> None:
        # Where the run has got to, on disk, for tabs that were not listening.
        #
        # The stream is in-process and never replayed, so a page opened -- or
        # reloaded -- mid-run has missed every `node_started` and cannot know
        # anything is happening: it offered to start the run again while the
        # run was executing, and drew the graph as though nothing were in
        # flight. The checkpoint after each super-step names what runs next,
        # which is what is executing during the one that follows, so recording
        # it here costs one small write per step rather than one per node.
        if event == "checkpoint":
            run.write_meta(progress={"next": payload.get("next") or [], "step": payload.get("step")})
        channel.publish({"event": event, "data": payload})

    session: InspectionSession | None = None
    try:
        config.require_model()
        if order.force:
            store.clear_results()

        index_stats = run.read_meta().get("index", {})
        run.set_status(STATUS_INSPECTING)
        emit("run_started", {"run_id": run.run_id, **index_stats})

        session = InspectionSession(
            run_id=run.run_id,
            files=run.file_contents(),
            store=store,
            config=config,
            emit=emit,
            index_stats=index_stats,
            spans=spans,
            checkpoints=True,
            breakpoints=order.breakpoints,
            breakpoints_after=order.breakpoints_after,
            cancelled=channel.cancelled.is_set,
        )

        if order.fresh:
            session.start(values=order.values, warm=not order.force)
        else:
            session.resume(values=order.resume_values, checkpoint_id=order.resume_from)

        aborted = False
        while session.interrupted and not aborted:
            # Recorded, not only emitted. The event stream is in-process and
            # cannot be replayed, so a tab opened -- or reloaded -- while the
            # run sits at a breakpoint never hears about it, and would offer to
            # start the run over rather than to carry it on. This is the same
            # fact on disk, where a reload can find it.
            parked = {"next": session.next_nodes, "checkpoint_id": session.checkpoint_id}
            run.set_status(STATUS_INTERRUPTED, parked=parked)
            emit("run_interrupted", {"run_id": run.run_id, **parked})
            command = _await_command(channel)
            if command.get("action") == "abort":
                aborted = True
                break
            run.set_status(STATUS_INSPECTING, parked=None)
            emit("run_resumed", {"run_id": run.run_id})
            try:
                session.resume(values=command.get("values"), checkpoint_id=command.get("checkpoint_id"))
            except ParallelStep as err:
                # An edit that cannot be attributed to a node. Reported and the
                # run left where it was, rather than torn down: the run is fine,
                # the question was not, and the answer is to ask a different one.
                emit("resume_refused", {"run_id": run.run_id, "error": str(err)})
                continue

        report = session.report()
        run.save_report(report)
        # `cancelled` rather than `done`, because `done` says the tree was read.
        # A partial report presented as complete is the coverage lie the whole
        # surface is built to avoid -- and `stats` already carries the numbers
        # that make the difference legible.
        stopped = session.stopped or channel.cancelled.is_set()
        run.set_status(
            STATUS_CANCELLED if stopped else STATUS_DONE,
            findings=len(report.findings),
            parked=None,
            progress=None,
        )
        emit(
            "run_finished",
            {"run_id": run.run_id, "findings": len(report.findings), "aborted": aborted},
        )
    except Exception as err:  # noqa: BLE001 - the failure is reported, not raised into the loop
        log.exception("inspection failed for run %s", run.run_id)
        channel.error = str(err)
        run.set_status(STATUS_FAILED, error=str(err), parked=None, progress=None)
        channel.publish({"event": "run_failed", "data": {"error": str(err)}})
    finally:
        if session is not None:
            session.close()
        store.close()
        spans.close()
        channel.waiting.clear()
        channel.finished.set()


def _await_command(channel: RunChannel) -> Dict[str, Any]:
    """Block until someone says what to do with a stopped run.

    A tab that was closed is never going to answer, so the wait is bounded and
    a timeout is read as an abort rather than as a reason to hold the run's
    tools open forever.
    """
    channel.waiting.set()
    try:
        return channel.commands.get(True, INTERRUPT_TIMEOUT_SECONDS)
    except queue.Empty:
        log.info("no answer for an interrupted run in %ss; giving up", INTERRUPT_TIMEOUT_SECONDS)
        return {"action": "abort"}
    finally:
        channel.waiting.clear()


def _validate_breakpoints(names: List[str]) -> List[str]:
    unknown = sorted(set(names) - set(NODES))
    if unknown:
        raise HTTPException(status_code=400, detail=f"unknown node(s): {', '.join(unknown)}")
    return list(dict.fromkeys(names))


def _spawn(run: Run, order: WorkOrder) -> RunChannel:
    """Put a worker on the run, reusing the channel anyone is already watching."""
    channel = _channel(run.run_id)
    channel.reclaim()
    threading.Thread(
        target=_inspect_worker,
        args=(run, channel, order),
        name=f"inspect-{run.run_id}",
        daemon=True,
    ).start()
    return channel


@router.post("/runs/{run_id}/inspect")
def start_inspection(run: RunDep, request: InspectRequest | None = None) -> Dict[str, Any]:
    """Start an inspection. Returns immediately; watch ``/events``."""
    options = request or InspectRequest()
    breakpoints = _validate_breakpoints(options.breakpoints)
    after = _validate_breakpoints(options.breakpoints_after)

    if _live_channel(run.run_id) is not None:
        return {"run_id": run.run_id, "status": STATUS_INSPECTING, "already_running": True}

    # Nothing to do is not the same as doing nothing.
    #
    # A chunk id is derived from its content, so pressing 검사 실행 again over an
    # unchanged tree analyses none of them: no model call, no finding, done in
    # milliseconds -- and a fresh start resets the debug record first, so the
    # call history of the run that *did* the work is thrown away to achieve it.
    # From the outside that is a button that destroys the trace and says 완료.
    #
    # So the run does not start. `force` is how you ask for the work anyway.
    if not options.force:
        store = run.store()
        try:
            pending = store.uninspected()
        finally:
            store.close()
        if not pending and run.read_meta().get("status"):
            return {
                "run_id": run.run_id,
                "status": run.read_meta().get("status", STATUS_DONE),
                "already_running": False,
                "nothing_to_do": True,
                "breakpoints": breakpoints,
                "breakpoints_after": after,
            }

    # Before anything is spawned, and after the two replies above, which do no
    # work and so need no model.
    #
    # `require_model` was checked inside the worker, so a deployment with no
    # `AGENT_MODEL` accepted the request with a 200, flipped the run to
    # `inspecting`, and then died: the reader pressed 검사 시작 and got a failed
    # scan rather than a button telling them what to configure. Which is the
    # opposite of what that check is for -- its own docstring says it exists so a
    # misconfigured deployment fails at startup rather than at chunk 400 of 600.
    # `/propose` has always answered this up front; this now does too.
    try:
        AgentConfig().require_model()
    except RuntimeError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err

    _spawn(
        run,
        WorkOrder(
            breakpoints=breakpoints,
            breakpoints_after=after,
            force=options.force,
            values=options.values,
        ),
    )
    return {
        "run_id": run.run_id,
        "status": STATUS_INSPECTING,
        "already_running": False,
        "breakpoints": breakpoints,
        "breakpoints_after": after,
    }


@router.post("/runs/{run_id}/resume")
def resume_inspection(run: RunDep, request: ResumeRequest | None = None) -> Dict[str, Any]:
    """Let a stopped run carry on, optionally with the state changed.

    Two ways in. A run still paused at a breakpoint is steered by handing the
    waiting worker its answer, which keeps the tools it already has open. A run
    whose worker is gone -- the server restarted, or it finished -- is picked up
    again from its checkpoints by a new worker.
    """
    options = request or ResumeRequest()
    if options.action not in ("resume", "abort"):
        raise HTTPException(status_code=400, detail=f"unknown action: {options.action}")

    channel = _live_channel(run.run_id)
    if channel is not None:
        if not channel.waiting.is_set():
            raise HTTPException(status_code=409, detail="this run is not stopped at a breakpoint")
        channel.commands.put(
            {"action": options.action, "values": options.values, "checkpoint_id": options.checkpoint_id}
        )
        return {"run_id": run.run_id, "resumed": options.action == "resume", "worker": "existing"}

    if options.action == "abort":
        raise HTTPException(status_code=409, detail="no run is in flight")
    if not run.checkpoints():
        raise HTTPException(status_code=409, detail="this run has no history to resume from")

    _spawn(
        run,
        WorkOrder(
            breakpoints=_validate_breakpoints(options.breakpoints),
            breakpoints_after=_validate_breakpoints(options.breakpoints_after),
            resume_from=options.checkpoint_id,
            resume_values=options.values,
            # Said outright rather than inferred from the values: "re-run from
            # here" writes nothing, and a resume that clears the history it is
            # resuming from would be worse than useless.
            resuming=True,
        ),
    )
    return {"run_id": run.run_id, "resumed": True, "worker": "new"}


@router.post("/runs/{run_id}/cancel")
def cancel_inspection(run: RunDep) -> Dict[str, Any]:
    """Stop a running scan, keeping what it has already found.

    Separate from `/resume {action: "abort"}`, which steers a worker *waiting* at
    a breakpoint by handing it an answer. That could not stop an ordinary scan:
    nothing reads `commands` unless the graph has parked, and the surface this
    serves sets no breakpoints, so 중단 refused every run it was pressed on with
    "not stopped at a breakpoint" -- true, and useless.

    So this sets a flag the graph loop *checks* rather than a message it waits
    for, and pushes the abort command as well, so the one route covers a parked
    worker too. The run ends as `cancelled` with the findings it had: stopping is
    not failing, and it is not finishing either.
    """
    channel = _live_channel(run.run_id)
    if channel is None or not channel.claimed:
        raise HTTPException(status_code=409, detail="지금 진행 중인 검사가 없습니다.")

    channel.cancelled.set()
    if channel.waiting.is_set():
        # Parked at a breakpoint, so it is waiting to be told rather than
        # looking to be stopped. Both, and whichever it is reads it.
        channel.commands.put({"action": "abort"})
    return {"run_id": run.run_id, "cancelled": True}


@router.get("/runs/{run_id}/events")
async def run_events(run: RunDep) -> StreamingResponse:
    """Server-sent events for an in-flight inspection.

    SSE rather than websockets: the traffic is one-way and this rides on the
    existing HTTP server with no extra protocol handling.
    """
    channel = _channel(run.run_id)

    async def stream() -> AsyncIterator[str]:
        # This reader's own queue. Every listener gets a copy of every event,
        # so a second tab watching the same run no longer takes frames away
        # from the first one.
        with channel.listen() as events:
            idle = 0.0
            while True:
                try:
                    message = await asyncio.to_thread(events.get, True, SSE_POLL_SECONDS)
                except queue.Empty:
                    if channel.finished.is_set():
                        break
                    idle += SSE_POLL_SECONDS
                    if idle >= SSE_KEEPALIVE_SECONDS:
                        idle = 0.0
                        yield ": keep-alive\n\n"
                    continue
                idle = 0.0
                yield f"event: {message['event']}\ndata: {json.dumps(message['data'])}\n\n"

        yield f"event: stream_closed\ndata: {json.dumps({'run_id': run.run_id})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/findings")
def run_findings(run: RunDep) -> Dict[str, Any]:
    """The report. Falls back to the store while a run is still in flight."""
    report = run.load_report()
    if report is not None:
        return report.model_dump()

    store = run.store()
    try:
        partial = Report(run_id=run.run_id, findings=[])
        partial.findings = [f for f in _validated(store.findings())]
        return partial.model_dump()
    finally:
        store.close()


def _validated(payloads: List[Dict[str, Any]]) -> List[Any]:
    from agent.schema import Finding

    out = []
    for payload in payloads:
        try:
            out.append(Finding.model_validate(payload))
        except ValueError:
            log.warning("discarding malformed stored finding: %s", payload.get("id"))
    return out


class ApplyRequest(BaseModel):
    finding_id: str


@router.post("/runs/{run_id}/propose")
def run_propose(run: RunDep, request: ApplyRequest) -> Dict[str, Any]:
    """Ask for code to fix a finding that arrived without any.

    A specialist proposes a fix while it is analysing, and only when the fix
    happens to fit the lines the anchor resolved to. When it does not -- and that
    is common -- the reader was left with a paragraph of advice and nothing to
    press. Telling somebody how to fix their code is not fixing it.

    So the fix becomes something that can be asked for. Narrower than the
    analysis: the judgement is already made and this is not a second opinion, it
    is one question about one span. The result is written back into the report,
    which means it arrives in exactly the shape the run would have produced --
    same builder, same re-indentation, same computed diff -- and lights up the
    apply button that was already there.

    Deliberately does not apply it. This writes to somebody's source, and the
    diff is shown first for the same reason it always was: offering to change a
    file without showing what would change asks for a decision nobody can make.
    """
    from agent.llm import StructuredCaller
    from agent.remediate import build as build_remediation
    from agent.remediate import propose as propose_fix

    report = run.load_report()
    if report is None:
        raise HTTPException(status_code=409, detail="this run has no completed report")

    at = next((i for i, f in enumerate(report.findings) if f.id == request.finding_id), None)
    if at is None:
        raise HTTPException(status_code=404, detail=f"unknown finding: {request.finding_id}")
    finding = report.findings[at]

    span = finding.primary
    text = run.read_file(span.file)
    if text is None:
        raise HTTPException(status_code=404, detail=f"cannot read {span.file}")

    lines = text.splitlines()
    if span.end_line > len(lines) or span.start_line < 1:
        raise HTTPException(status_code=409, detail="the file no longer has the lines this finding is anchored to")

    # Read from the run rather than from the report: the fix has to replace what
    # is there now, and `/apply` refuses anyway if those two have diverged.
    excerpt = "\n".join(lines[span.start_line - 1 : span.end_line])

    config = AgentConfig()
    try:
        config.require_model()
    except RuntimeError as err:
        # A deployment with no endpoint configured is a normal state here -- the
        # rest of this page reads a recorded run and needs no model at all -- so
        # it is an answer, not a crash.
        raise HTTPException(status_code=503, detail=str(err)) from err

    candidate = propose_fix(
        StructuredCaller(config),
        title=finding.title,
        explanation=finding.explanation,
        span=span,
        excerpt=excerpt,
        context=text,
    )
    if not candidate.ok:
        # Said rather than swallowed. A model that ran out of completion tokens
        # mid-object is a different thing from one that judged the line
        # unfixable, and the reader was being told the second when it was the
        # first.
        raise HTTPException(
            status_code=503 if candidate.reason == "transport" else 409,
            detail=f"고칠 코드를 만들지 못했습니다 ({candidate.reason}).",
        )
    if not (candidate.value.replacement or "").strip():
        raise HTTPException(status_code=409, detail="이 문제는 해당 줄만 바꿔서는 고칠 수 없습니다.")

    built = build_remediation(candidate.value, span, text)
    if not built.replacement:
        # Re-indented to exactly what is already there: a fix that changes
        # nothing, which is not a fix.
        raise HTTPException(status_code=409, detail="제안된 코드가 지금 코드와 같습니다.")

    # Kept, so the diff a reader approves is the one the patch is built from,
    # and so a reload does not lose it.
    report.findings[at] = finding.model_copy(update={"remediation": built})
    run.save_report(report)

    return {
        "run_id": run.run_id,
        "finding_id": finding.id,
        "remediation": built.model_dump(),
    }
