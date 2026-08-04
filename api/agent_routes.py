"""HTTP surface for the LLM agent: upload, inspect, stream, report.

Mounted on the existing FastAPI app rather than run as a second service, so
there is one dev server and one CORS policy. The dependency direction is the
same as for ``ssat``: ``api`` imports ``agent``, and ``agent`` imports neither
``ssat`` nor ``gnn``.

An inspection takes minutes, so it does not happen inside the request that
starts it. ``POST /inspect`` hands the work to a thread and returns immediately;
progress is streamed over SSE from ``/events``, and the finished report is
fetched from ``/findings``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.config import AgentConfig
from agent.endpoint import list_models
from agent.tracing import status as tracing_status
from agent.graph.build import graph_shape, run_inspection
from agent.index import build_index
from agent.paths import PathEscape, resolve_within
from agent.runs import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_INDEXING,
    STATUS_INSPECTING,
    RunPaths,
    UploadRejected,
    diff_reports,
    extract_zip,
    get_run,
    iter_all_files,
    list_runs,
    new_run,
    write_files,
)
from agent.schema import Report

log = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

#: How long the SSE generator waits on the queue before emitting a keep-alive.
#: Proxies close an idle connection, and a chunk can take longer than that.
SSE_POLL_SECONDS = 1.0
SSE_KEEPALIVE_SECONDS = 15.0


@dataclass
class RunChannel:
    """Progress events for one in-flight run.

    A plain thread-safe queue rather than an asyncio one: the producer is the
    inspection thread and the consumer is the event loop, so the queue has to
    work across that boundary.
    """

    events: "queue.Queue[dict[str, Any]]" = field(default_factory=queue.Queue)
    finished: threading.Event = field(default_factory=threading.Event)
    error: Optional[str] = None


#: In-process only. A restart loses the stream but not the run: the report is on
#: disk, and re-requesting the inspection resumes from the store.
_channels: Dict[str, RunChannel] = {}
_channels_lock = threading.Lock()


def _channel(run_id: str) -> RunChannel:
    with _channels_lock:
        return _channels.setdefault(run_id, RunChannel())


def _require_run(run_id: str) -> RunPaths:
    paths = get_run(run_id)
    if paths is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {run_id}")
    return paths


class InspectRequest(BaseModel):
    """Options for starting an inspection."""

    #: Re-inspect chunks that already have results. Off by default, because the
    #: whole point of content-derived chunk ids is that unchanged code is free.
    force: bool = False


class WriteFileRequest(BaseModel):
    """Create or replace one file in a run."""

    path: str
    content: str


class DiffRequest(BaseModel):
    """Compare this run against another."""

    against: str


@router.get("/health")
def agent_health(probe: bool = False) -> Dict[str, Any]:
    """Whether the agent is configured well enough to run.

    Configuration is answered from the environment, with no network call, so
    this stays usable as a liveness probe. Pass ``?probe=true`` to also ask the
    endpoint what it serves -- worth it when diagnosing an AGENT_MODEL that does
    not match any served id, which is the usual first failure.
    """
    config = AgentConfig()
    body: Dict[str, Any] = {
        "configured": bool(config.model),
        "base_url": config.base_url,
        "model": config.model or None,
        "sandbox": config.sandbox,
        "tools_enabled": config.enable_tools,
        "runs_dir": str(config.runs_dir),
        "tracing": tracing_status(),
    }
    if probe:
        served = list_models(config.base_url)
        body["reachable"] = bool(served)
        body["served_models"] = served
        body["model_is_served"] = config.model in served if (config.model and served) else False
    return body


@router.get("/traces")
def agent_traces(limit: int = 25) -> Dict[str, Any]:
    """Recent LangSmith runs for the configured project.

    Read server-side because the API key belongs on the server, and because
    LangSmith cannot be embedded: it serves `frame-ancestors 'self'`, so an
    iframe of the hosted app renders blank. Listing the runs here and deep
    linking out is the version that works.
    """
    status = tracing_status()
    body: Dict[str, Any] = {"tracing": status, "runs": [], "error": None}
    if not status["enabled"] or not status["api_key_set"]:
        return body

    try:
        from langsmith import Client

        client = Client()
        runs = list(client.list_runs(project_name=status["project"], is_root=True, limit=max(1, min(limit, 100))))
    except Exception as err:  # noqa: BLE001 - a tracing backend outage is not a server error
        body["error"] = str(err)
        return body

    for run in runs:
        body["runs"].append(
            {
                "id": str(run.id),
                "name": run.name,
                "status": run.status,
                "start_time": run.start_time.isoformat() if run.start_time else None,
                "latency_ms": (
                    int((run.end_time - run.start_time).total_seconds() * 1000)
                    if run.end_time and run.start_time
                    else None
                ),
                "tokens": run.total_tokens,
                "error": run.error,
                "url": _trace_url(run),
                "tags": list(run.tags or []),
            }
        )
    return body


#: LLM inputs and outputs are large; a trace view needs them readable, not
#: complete. The full payload is one click away in LangSmith.
MAX_PAYLOAD_CHARS = 12_000


def _clip(value: Any) -> Any:
    """Shrink a payload to something a browser can render."""
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= MAX_PAYLOAD_CHARS:
        return value
    return {"_truncated": True, "_chars": len(text), "preview": text[:MAX_PAYLOAD_CHARS]}


def _span(run: Any) -> Dict[str, Any]:
    """One node of a trace tree."""
    return {
        "id": str(run.id),
        "parent_id": str(run.parent_run_id) if run.parent_run_id else None,
        "name": run.name,
        "run_type": run.run_type,
        "status": run.status,
        "error": run.error,
        "start_time": run.start_time.isoformat() if run.start_time else None,
        "latency_ms": (
            int((run.end_time - run.start_time).total_seconds() * 1000) if run.end_time and run.start_time else None
        ),
        "tokens": run.total_tokens,
        "cost": run.total_cost,
        "tags": list(run.tags or []),
        "metadata": (run.extra or {}).get("metadata", {}),
        "inputs": _clip(run.inputs) if run.inputs else None,
        "outputs": _clip(run.outputs) if run.outputs else None,
        "dotted_order": run.dotted_order,
        "url": _trace_url(run),
    }


@router.get("/traces/{trace_id}")
def agent_trace(trace_id: str) -> Dict[str, Any]:
    """Every span of one trace, ordered so the tree can be rebuilt here.

    This is the agent-structure and tool-call view, rendered in this app rather
    than linked out to. LangSmith encodes tree position in `dotted_order`, so
    sorting on it yields a valid parent-before-child sequence without a second
    round trip per node.
    """
    status = tracing_status()
    if not status["enabled"] or not status["api_key_set"]:
        raise HTTPException(status_code=409, detail="tracing is not configured")

    try:
        from langsmith import Client

        spans = list(Client().list_runs(project_name=status["project"], trace_id=trace_id))
    except Exception as err:  # noqa: BLE001 - an upstream outage is not a server error
        raise HTTPException(status_code=502, detail=f"LangSmith: {err}") from err

    spans.sort(key=lambda r: (r.dotted_order or "", r.start_time or 0))
    return {"trace_id": trace_id, "spans": [_span(run) for run in spans]}


def _trace_url(run: Any) -> str | None:
    """The run's page in LangSmith, if the SDK can build one."""
    try:
        return str(run.url)
    except Exception:  # noqa: BLE001 - url is a convenience, not a contract
        return None


@router.get("/graph")
def agent_graph() -> Dict[str, Any]:
    """The inspection graph's nodes and edges.

    A property of the code, not of a run, so it answers before anything has
    been inspected -- the structure is the thing you want to look at first.
    """
    return graph_shape()


@router.get("/runs")
def get_runs() -> Dict[str, Any]:
    return {"runs": list_runs()}


@router.post("/runs")
async def create_run(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    """Upload source and index it.

    Accepts either a single ``.zip`` or a set of individual files. Indexing runs
    here rather than in the background because it is seconds, not minutes, and
    the editor needs the file list before it can render anything.
    """
    if not files:
        raise HTTPException(status_code=400, detail="no files uploaded")

    paths = new_run()
    try:
        if len(files) == 1 and (files[0].filename or "").lower().endswith(".zip"):
            archive = paths.base / "upload.zip"
            archive.write_bytes(await files[0].read())
            written = extract_zip(archive, paths.source)
            archive.unlink(missing_ok=True)
        else:
            payload = {(f.filename or "unnamed"): await f.read() for f in files}
            written = write_files(paths.source, payload)
    except UploadRejected as err:
        paths.set_status(STATUS_FAILED, error=str(err))
        raise HTTPException(status_code=400, detail=str(err)) from err

    if written == 0:
        raise HTTPException(status_code=400, detail="upload contained no files")

    paths.set_status(STATUS_INDEXING)
    store = paths.store()
    try:
        result = build_index(paths.source, store)
    finally:
        store.close()
    paths.write_meta(status="indexed", index=result.as_dict(), uploaded=written)

    return {
        "run_id": paths.run_id,
        "uploaded": written,
        "index": result.as_dict(),
        "files": sorted(iter_all_files(paths)),
    }


@router.post("/runs/new")
def create_empty_run() -> Dict[str, Any]:
    """An empty run to paste into.

    The upload endpoint needs files; starting from a blank editor does not have
    any yet, and making the user save a file to disk first to try one snippet
    is a poor trade.
    """
    paths = new_run()
    paths.write_meta(status="indexed", index={}, uploaded=0)
    return {"run_id": paths.run_id, "uploaded": 0, "index": {}, "files": []}


def _reindex(paths: RunPaths) -> Dict[str, int]:
    """Rebuild the index after the tree changed.

    Cheap to do on every edit and necessary for correctness: the chunk store is
    what the inspection walks. Chunk ids are content-derived, so re-inspecting
    afterwards only pays for the chunks that actually changed.
    """
    store = paths.store()
    try:
        store.conn.execute("DELETE FROM chunks")
        store.conn.execute("DELETE FROM links")
        store.conn.commit()
        result = build_index(paths.source, store)
    finally:
        store.close()
    stats = result.as_dict()
    paths.write_meta(index=stats)
    return stats


@router.put("/runs/{run_id}/file")
def write_run_file(run_id: str, req: WriteFileRequest) -> Dict[str, Any]:
    """Write a file into the run and re-index.

    Confined with the same resolver the tools use: the path comes from the
    browser, so `../` and absolute paths are rejected rather than reinterpreted.
    """
    paths = _require_run(run_id)
    try:
        resolved = resolve_within(paths.source, req.path)
    except PathEscape as err:
        raise HTTPException(status_code=400, detail=str(err)) from err

    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(req.content, encoding="utf-8")
    return {"path": req.path, "index": _reindex(paths), "files": sorted(iter_all_files(paths))}


@router.delete("/runs/{run_id}/file")
def delete_run_file(run_id: str, path: str) -> Dict[str, Any]:
    paths = _require_run(run_id)
    try:
        resolved = resolve_within(paths.source, path)
    except PathEscape as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"no such file: {path}")

    resolved.unlink()
    # Findings for the deleted file would otherwise linger in the report.
    store = paths.store()
    try:
        store.conn.execute("DELETE FROM findings WHERE file = ?", (path,))
        store.conn.commit()
    finally:
        store.close()
    return {"deleted": path, "index": _reindex(paths), "files": sorted(iter_all_files(paths))}


@router.get("/runs/{run_id}")
def run_detail(run_id: str) -> Dict[str, Any]:
    paths = _require_run(run_id)
    return {"run_id": run_id, **paths.read_meta()}


@router.get("/runs/{run_id}/spans")
def run_spans(run_id: str) -> Dict[str, Any]:
    """The call tree of this run's last inspection.

    Recorded locally, so the debug view works with no LangSmith account, no key
    and no egress -- and can be shown to a user, which the hosted view cannot
    (it serves ``frame-ancestors 'self'`` and needs a login besides).

    Readable mid-run: the store is WAL, so this returns what has landed so far
    with unfinished spans still marked ``running``.
    """
    paths = _require_run(run_id)
    if not paths.trace_db.exists():
        return {"run_id": run_id, "spans": [], "summary": _span_summary([])}

    spans = paths.spans()
    try:
        rows = [span.as_dict() for span in spans.spans()]
    finally:
        spans.close()
    return {"run_id": run_id, "spans": rows, "summary": _span_summary(rows)}


def _span_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Headline numbers, computed here so every client agrees on them."""
    latencies = [row["latency_ms"] for row in rows if row.get("latency_ms") is not None]
    return {
        "spans": len(rows),
        "llm_calls": sum(1 for row in rows if row["kind"] == "llm"),
        "tool_calls": sum(1 for row in rows if row["kind"] == "tool"),
        "errors": sum(1 for row in rows if row["status"] == "error"),
        "running": sum(1 for row in rows if row["status"] == "running"),
        "tokens": sum(row["tokens"] or 0 for row in rows),
        "total_ms": sum(latencies),
    }


@router.get("/runs/{run_id}/checkpoints")
def run_checkpoints(run_id: str) -> Dict[str, Any]:
    """This run's state after each super-step, oldest first.

    The trace says what was called; this says what the graph *knew* at each
    step -- what was still queued, what the last node wrote, where it would go
    next. One thread per run, so this is only ever this run's history.
    """
    paths = _require_run(run_id)
    steps = paths.checkpoints()
    return {"run_id": run_id, "checkpoints": steps, "count": len(steps)}


@router.get("/runs/{run_id}/thread")
def run_thread(run_id: str) -> Dict[str, Any]:
    """The run as conversations -- one per chunk, in the order they happened.

    A span tree shows the machinery. This shows the exchange: what the agent was
    asked, what it answered, which tools it reached for and what came back.
    """
    paths = _require_run(run_id)
    if not paths.trace_db.exists():
        return {"run_id": run_id, "threads": []}

    spans = paths.spans()
    try:
        rows = spans.spans()
    finally:
        spans.close()

    by_id = {span.id: span for span in rows}
    threads: Dict[str, Dict[str, Any]] = {}

    for span in rows:
        if span.kind != "llm":
            continue
        # Group by chunk, falling back to the node: one chunk is one
        # conversation, which is the unit the agent actually reasons in.
        key = str(span.meta.get("chunk_id") or span.meta.get("langgraph_node") or "run")
        thread = threads.setdefault(
            key,
            {
                "id": key,
                "symbol": span.meta.get("symbol"),
                "file": span.meta.get("file"),
                "turns": [],
                "tokens": 0,
            },
        )
        thread["tokens"] += span.tokens or 0
        thread["turns"].append(_turn(span, by_id))

    return {"run_id": run_id, "threads": list(threads.values())}


def _turn(span: Any, by_id: Dict[str, Any]) -> Dict[str, Any]:
    """One model call as an exchange: what went in, what came back, what ran."""
    inputs = span.inputs if isinstance(span.inputs, dict) else {}
    outputs = span.outputs if isinstance(span.outputs, dict) else {}
    messages = inputs.get("messages")
    if not isinstance(messages, list):
        # A completion-style call has prompts rather than messages; presented
        # the same way so the view does not need two shapes.
        messages = [{"role": "human", "content": text} for text in inputs.get("prompts", [])]

    return {
        "id": span.id,
        "step": span.meta.get("step") or span.name,
        "name": span.name,
        "messages": messages,
        "reply": "\n".join(outputs.get("text", [])) or None,
        "tool_calls": outputs.get("tool_calls") or [],
        "tools": [
            {
                "name": child.name,
                "inputs": child.inputs,
                "outputs": child.outputs,
                "error": child.error,
                "latency_ms": child.latency_ms,
            }
            for child in by_id.values()
            if child.parent_id == span.id and child.kind == "tool"
        ],
        "latency_ms": span.latency_ms,
        "tokens": span.tokens,
        "error": span.error,
    }


@router.get("/runs/{run_id}/files")
def run_files(run_id: str) -> Dict[str, Any]:
    paths = _require_run(run_id)
    return {"run_id": run_id, "files": sorted(iter_all_files(paths))}


@router.get("/runs/{run_id}/file")
def run_file(run_id: str, path: str) -> Dict[str, Any]:
    """One file's text, for the editor.

    Confined with the same resolver the tools use, because this endpoint takes
    a path straight from a query string.
    """
    paths = _require_run(run_id)
    try:
        resolved = resolve_within(paths.source, path)
    except PathEscape as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    if not resolved.is_file():
        raise HTTPException(status_code=404, detail=f"no such file: {path}")

    return {
        "path": path,
        "content": resolved.read_text(encoding="utf-8", errors="replace"),
        "language": _language_for(resolved),
    }


#: Extension -> Monaco language id. Monaco's own names differ from tree-sitter's.
_MONACO_LANGUAGES = {
    ".c": "c",
    ".h": "c",
    ".cc": "cpp",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".hpp": "cpp",
    ".hh": "cpp",
    ".java": "java",
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".cs": "csharp",
    ".json": "json",
    ".md": "markdown",
}


def _language_for(path: Path) -> str:
    return _MONACO_LANGUAGES.get(path.suffix.lower(), "plaintext")


def _inspect_worker(paths: RunPaths, channel: RunChannel, force: bool) -> None:
    """Run the inspection on a worker thread, publishing progress."""
    config = AgentConfig()
    store = paths.store()
    # One trace and one checkpoint thread per inspection: the previous attempt
    # describes work about to be redone, and two interleaved in one history are
    # unreadable.
    paths.reset_debug()
    spans = paths.spans()

    def emit(event: str, payload: dict[str, Any]) -> None:
        channel.events.put({"event": event, "data": payload})

    try:
        config.require_model()
        if force:
            store.conn.execute("DELETE FROM inspected")
            store.conn.execute("DELETE FROM findings")
            store.conn.commit()

        index_stats = paths.read_meta().get("index", {})
        paths.set_status(STATUS_INSPECTING)
        emit("run_started", {"run_id": paths.run_id, **index_stats})

        report = run_inspection(
            run_id=paths.run_id,
            root=paths.source,
            store=store,
            config=config,
            emit=emit,
            index_stats=index_stats,
            spans=spans,
            checkpoints=paths.checkpoint_db,
        )
        paths.save_report(report)
        paths.set_status(STATUS_DONE, findings=len(report.findings))
        emit("run_finished", {"run_id": paths.run_id, "findings": len(report.findings)})
    except Exception as err:  # noqa: BLE001 - the failure is reported, not raised into the loop
        log.exception("inspection failed for run %s", paths.run_id)
        channel.error = str(err)
        paths.set_status(STATUS_FAILED, error=str(err))
        channel.events.put({"event": "run_failed", "data": {"error": str(err)}})
    finally:
        store.close()
        spans.close()
        channel.finished.set()


@router.post("/runs/{run_id}/inspect")
def start_inspection(run_id: str, request: InspectRequest | None = None) -> Dict[str, Any]:
    """Start an inspection. Returns immediately; watch ``/events``."""
    paths = _require_run(run_id)
    options = request or InspectRequest()

    with _channels_lock:
        existing = _channels.get(run_id)
        if existing is not None and not existing.finished.is_set():
            return {"run_id": run_id, "status": STATUS_INSPECTING, "already_running": True}
        channel = RunChannel()
        _channels[run_id] = channel

    thread = threading.Thread(
        target=_inspect_worker,
        args=(paths, channel, options.force),
        name=f"inspect-{run_id}",
        daemon=True,
    )
    thread.start()
    return {"run_id": run_id, "status": STATUS_INSPECTING, "already_running": False}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """Server-sent events for an in-flight inspection.

    SSE rather than websockets: the traffic is one-way and this rides on the
    existing HTTP server with no extra protocol handling.
    """
    _require_run(run_id)
    channel = _channel(run_id)

    async def stream() -> AsyncIterator[str]:
        idle = 0.0
        while True:
            try:
                message = await asyncio.to_thread(channel.events.get, True, SSE_POLL_SECONDS)
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

        yield f"event: stream_closed\ndata: {json.dumps({'run_id': run_id})}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/runs/{run_id}/findings")
def run_findings(run_id: str) -> Dict[str, Any]:
    """The report. Falls back to the store while a run is still in flight."""
    paths = _require_run(run_id)
    report = paths.load_report()
    if report is not None:
        return report.model_dump()

    store = paths.store()
    try:
        partial = Report(run_id=run_id, findings=[])
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


@router.post("/runs/{run_id}/diff")
def run_diff(run_id: str, request: DiffRequest) -> Dict[str, Any]:
    """New / fixed / unchanged against another run.

    Works because finding ids are content-derived: a finding that shifted
    because a line was inserted above it counts as unchanged.
    """
    current = _require_run(run_id)
    other = get_run(request.against)
    if other is None:
        raise HTTPException(status_code=404, detail=f"unknown run: {request.against}")

    after = current.load_report()
    before = other.load_report()
    if after is None or before is None:
        raise HTTPException(status_code=409, detail="both runs must have a completed report")

    return diff_reports(before, after).model_dump()
