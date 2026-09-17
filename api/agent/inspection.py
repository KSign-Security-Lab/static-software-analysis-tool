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
from agent.index import ChunkStore
from agent.runs import (
    STATUS_CANCELLED,
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_INSPECTING,
    STATUS_INTERRUPTED,
    Run,
)
from agent.schema import Report
from agent.trace import SpanStore

from .channels import (
    INTERRUPT_TIMEOUT_SECONDS,
    SSE_KEEPALIVE_SECONDS,
    SSE_POLL_SECONDS,
    STREAM_START_GRACE_SECONDS,
    RunChannel,
    _channel,
    _live_channel,
)
from .deps import RunDep

log = logging.getLogger(__name__)
router = APIRouter()


class InspectRequest(BaseModel):
    force: bool = False
    breakpoints: List[str] = []
    breakpoints_after: List[str] = []
    values: Optional[Dict[str, Any]] = None


class ResumeRequest(BaseModel):
    action: str = "resume"
    values: Optional[Dict[str, Any]] = None
    checkpoint_id: Optional[str] = None
    breakpoints: List[str] = []
    breakpoints_after: List[str] = []


@dataclass
class WorkOrder:
    breakpoints: List[str] = field(default_factory=list)
    breakpoints_after: List[str] = field(default_factory=list)
    force: bool = False
    values: Optional[Dict[str, Any]] = None
    resume_from: Optional[str] = None
    resume_values: Optional[Dict[str, Any]] = None
    resuming: bool = False

    @property
    def fresh(self) -> bool:
        return not self.resuming


def _inspect_worker(run: Run, channel: RunChannel, order: WorkOrder) -> None:
    def emit(event: str, payload: dict[str, Any]) -> None:
        if event == "checkpoint":
            run.write_meta(progress={"next": payload.get("next") or [], "step": payload.get("step")})
        channel.publish({"event": event, "data": payload})

    session: InspectionSession | None = None
    store: ChunkStore | None = None
    spans: SpanStore | None = None
    try:
        config = AgentConfig()
        store = run.store()
        if order.fresh:
            run.reset_debug()
        spans = run.spans()

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
        while session.interrupted and not aborted and not channel.cancelled.is_set():
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
                emit("resume_refused", {"run_id": run.run_id, "error": str(err)})
                continue

        report = session.report()
        run.save_report(report)
        stopped = session.stopped or channel.cancelled.is_set()
        run.set_status(
            STATUS_CANCELLED if stopped else STATUS_DONE,
            findings=len(report.findings),
            parked=None,
            progress=None,
        )
        emit(
            "run_finished",
            {"run_id": run.run_id, "findings": len(report.findings), "aborted": aborted or stopped},
        )
    except Exception as err:  # noqa: BLE001 - the failure is reported, not raised into the loop
        log.exception("inspection failed for run %s", run.run_id)
        channel.error = str(err)
        run.set_status(STATUS_FAILED, error=str(err), parked=None, progress=None)
        channel.publish({"event": "run_failed", "data": {"error": str(err)}})
    finally:
        for closing in (session, store, spans):
            if closing is None:
                continue
            try:
                closing.close()
            except Exception:  # noqa: BLE001 - a failed close must not strand the run
                log.exception("closing %s for run %s", type(closing).__name__, run.run_id)
        channel.waiting.clear()
        channel.finished.set()


def _await_command(channel: RunChannel) -> Dict[str, Any]:
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


def _spawn(run: Run, order: WorkOrder) -> RunChannel | None:
    channel = _channel(run.run_id)
    if not channel.claim():
        return None
    worker = threading.Thread(
        target=_inspect_worker,
        args=(run, channel, order),
        name=f"inspect-{run.run_id}",
        daemon=True,
    )
    channel.worker = worker
    try:
        worker.start()
    except BaseException:
        channel.finished.set()
        raise
    return channel


@router.post("/runs/{run_id}/inspect")
def start_inspection(run: RunDep, request: InspectRequest | None = None) -> Dict[str, Any]:
    options = request or InspectRequest()
    breakpoints = _validate_breakpoints(options.breakpoints)
    after = _validate_breakpoints(options.breakpoints_after)

    if _live_channel(run.run_id) is not None:
        return {"run_id": run.run_id, "status": STATUS_INSPECTING, "already_running": True}

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

    try:
        AgentConfig().require_model()
    except RuntimeError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err

    if (
        _spawn(
            run,
            WorkOrder(
                breakpoints=breakpoints,
                breakpoints_after=after,
                force=options.force,
                values=options.values,
            ),
        )
        is None
    ):
        return {"run_id": run.run_id, "status": STATUS_INSPECTING, "already_running": True}
    return {
        "run_id": run.run_id,
        "status": STATUS_INSPECTING,
        "already_running": False,
        "breakpoints": breakpoints,
        "breakpoints_after": after,
    }


@router.post("/runs/{run_id}/resume")
def resume_inspection(run: RunDep, request: ResumeRequest | None = None) -> Dict[str, Any]:
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

    if (
        _spawn(
            run,
            WorkOrder(
                breakpoints=_validate_breakpoints(options.breakpoints),
                breakpoints_after=_validate_breakpoints(options.breakpoints_after),
                resume_from=options.checkpoint_id,
                resume_values=options.values,
                resuming=True,
            ),
        )
        is None
    ):
        raise HTTPException(status_code=409, detail="this run is already in flight")
    return {"run_id": run.run_id, "resumed": True, "worker": "new"}


@router.post("/runs/{run_id}/cancel")
def cancel_inspection(run: RunDep) -> Dict[str, Any]:
    channel = _live_channel(run.run_id)
    if channel is None or not channel.claimed:
        raise HTTPException(status_code=409, detail="지금 진행 중인 검사가 없습니다.")

    channel.cancelled.set()
    if channel.waiting.is_set():
        channel.commands.put({"action": "abort"})
    return {"run_id": run.run_id, "cancelled": True}


def _progress_now(run: Run) -> Dict[str, Any] | None:
    """Where the run has got to, for a client that just attached.

    The stream only carries what happens next, so a tab that navigates away and
    back learns nothing until the current chunk ends -- minutes, with a model in
    the loop, during which the progress bar has no numbers and hides itself.
    """
    store = run.store()
    total = len(store.order())
    remaining = len(store.uninspected())
    # Only when some of it is already done. A run nobody has started has nothing
    # to report, and announcing 0% would put a bar where there was none.
    if not total or remaining >= total:
        return None
    return {"run_id": run.run_id, "remaining": remaining, "total": total}


@router.get("/runs/{run_id}/events")
async def run_events(run: RunDep) -> StreamingResponse:
    channel = _channel(run.run_id)

    async def stream() -> AsyncIterator[str]:
        snapshot = await asyncio.to_thread(_progress_now, run)
        if snapshot is not None:
            yield f"event: progress\ndata: {json.dumps(snapshot)}\n\n"
        with channel.listen() as events:
            watching = channel.live
            idle = waited = 0.0
            while True:
                try:
                    message = await asyncio.to_thread(events.get, True, SSE_POLL_SECONDS)
                except queue.Empty:
                    if channel.live:
                        watching = True
                    elif watching:
                        break
                    else:
                        waited += SSE_POLL_SECONDS
                        if waited >= STREAM_START_GRACE_SECONDS:
                            break
                    idle += SSE_POLL_SECONDS
                    if idle >= SSE_KEEPALIVE_SECONDS:
                        idle = 0.0
                        yield ": keep-alive\n\n"
                    continue
                idle = waited = 0.0
                yield f"event: {message['event']}\ndata: {json.dumps(message['data'])}\n\n"

        yield f"event: stream_closed\ndata: {json.dumps({'run_id': run.run_id})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/findings")
def run_findings(run: RunDep) -> Dict[str, Any]:
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
    from agent.llm import StructuredCaller
    from agent.remediate import build as build_remediation
    from agent.remediate import propose as propose_fix
    from agent.remediate import window_around

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

    excerpt = "\n".join(lines[span.start_line - 1 : span.end_line])
    config = AgentConfig()
    try:
        config.require_model()
    except RuntimeError as err:
        raise HTTPException(status_code=503, detail=str(err)) from err

    candidate = propose_fix(
        StructuredCaller(config),
        title=finding.title,
        explanation=finding.explanation,
        span=span,
        excerpt=excerpt,
        context=window_around(text, span, config.input_chars()),
    )
    if not candidate.ok:
        why = {
            "too_long": "분석할 코드가 모델이 한 번에 볼 수 있는 양을 넘었습니다.",
            "length": "모델이 답을 끝맺지 못했습니다. 더 큰 모델이 필요할 수 있습니다.",
            "refused": "모델이 알아볼 수 없는 형식으로 답했습니다.",
        }.get(candidate.reason or "", "모델에 연결하지 못했습니다.")
        raise HTTPException(
            status_code=503 if candidate.reason == "transport" else 409,
            detail=f"고칠 코드를 만들지 못했습니다. {why}",
        )
    if not (candidate.value.replacement or "").strip():
        raise HTTPException(status_code=409, detail="이 문제는 해당 줄만 바꿔서는 고칠 수 없습니다.")

    built = build_remediation(candidate.value, span, text)
    if not built.replacement:
        raise HTTPException(status_code=409, detail="제안된 코드가 지금 코드와 같습니다.")

    report.findings[at] = finding.model_copy(update={"remediation": built})
    run.save_report(report)

    return {
        "run_id": run.run_id,
        "finding_id": finding.id,
        "remediation": built.model_dump(),
    }
