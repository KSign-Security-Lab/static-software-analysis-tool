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
import time
from dataclasses import dataclass, field
from pathlib import Path
from contextlib import contextmanager
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agent.config import AgentConfig
from agent.endpoint import list_models
from agent.tracing import status as tracing_status
from agent.graph.build import NODES, graph_shape
from agent.graph.session import InspectionSession, ParallelStep
from agent.graph.state import initial_state
from agent.index import build_index
from agent.knowledge import read_graph, write_graph
from graphify import to_json as knowledge_json
from agent.llm import StructuredCaller
from agent.paths import PathEscape, resolve_within
from agent import promptstore as prompt_store
from agent.promptstore import lens_prompt
from agent.runs import (
    STATUS_DONE,
    STATUS_FAILED,
    STATUS_INDEXING,
    STATUS_INSPECTING,
    STATUS_INTERRUPTED,
    RunPaths,
    UploadRejected,
    delete_run,
    describe_run,
    diff_reports,
    extract_zip,
    get_run,
    iter_all_files,
    list_runs,
    new_run,
    write_files,
)
from agent.schema import LENSES, Report

log = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["agent"])

#: How long the SSE generator waits on the queue before emitting a keep-alive.
#: Proxies close an idle connection, and a chunk can take longer than that.
SSE_POLL_SECONDS = 1.0
SSE_KEEPALIVE_SECONDS = 15.0


#: How long a run paused at a breakpoint waits to be told what to do before it
#: gives up and lets go of its tools. A person is expected to answer; an
#: abandoned tab is not, and it would hold an MCP subprocess open indefinitely.
INTERRUPT_TIMEOUT_SECONDS = 30 * 60


@dataclass
class RunChannel:
    """The two-way link with one in-flight run.

    Plain thread-safe queues rather than asyncio ones: the run is on a worker
    thread and the requests are on the event loop, so both have to work across
    that boundary. ``publish`` carries progress out; ``commands`` carries the
    answer back in when the run stops at a breakpoint and waits.

    Progress fans out: every listener gets its own queue and every event is
    copied into all of them. There used to be a single queue that each reader
    popped from, which meant two readers on one run *split* its events -- each
    frame reaching exactly one of them, and neither seeing a whole run. Two
    browser tabs was enough to trigger it.
    """

    commands: "queue.Queue[dict[str, Any]]" = field(default_factory=queue.Queue)
    finished: threading.Event = field(default_factory=threading.Event)
    #: Set while the run is stopped at a breakpoint, so a resume request knows
    #: whether to steer the live worker or start a new one.
    waiting: threading.Event = field(default_factory=threading.Event)
    #: Whether a worker was ever put on this channel. A channel opened by a
    #: listener is not a run in flight -- without this, watching a run before
    #: starting it would make it look like it had already started.
    claimed: bool = False
    error: Optional[str] = None

    _listeners: "set[queue.Queue[dict[str, Any]]]" = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def publish(self, message: Dict[str, Any]) -> None:
        """Hand one event to every listener.

        Events published with nobody attached are dropped rather than buffered.
        That is deliberate: the stream is documented as not replayable, clients
        read their state over REST and use this only as a signal, and an
        unbounded backlog for a listener that may never arrive is a leak.
        """
        with self._lock:
            listeners = list(self._listeners)
        for listener in listeners:
            listener.put(message)

    @contextmanager
    def listen(self) -> "Iterator[queue.Queue[dict[str, Any]]]":
        """Attach a queue for as long as one reader is reading it."""
        mine: "queue.Queue[dict[str, Any]]" = queue.Queue()
        with self._lock:
            self._listeners.add(mine)
        try:
            yield mine
        finally:
            with self._lock:
                self._listeners.discard(mine)

    @property
    def listeners(self) -> int:
        with self._lock:
            return len(self._listeners)

    def reclaim(self) -> None:
        """Ready this channel for another worker, keeping listeners attached.

        The watcher holds this object, so it is reset rather than replaced --
        swapping it would leave whoever is watching listening to a queue nothing
        writes to any more.
        """
        with self._lock:
            stale = list(self._listeners)
        for listener in [*stale, self.commands]:
            while True:
                try:
                    listener.get_nowait()
                except queue.Empty:
                    break
        self.finished.clear()
        self.waiting.clear()
        self.error = None
        self.claimed = True


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


class StateRequest(BaseModel):
    """Write state over a checkpoint."""

    values: Dict[str, Any]
    checkpoint_id: Optional[str] = None
    #: Whose write this stands in for. Inferred from the checkpoint when absent.
    as_node: Optional[str] = None


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


@router.get("/graph")
def agent_graph() -> Dict[str, Any]:
    """The inspection graph's nodes and edges.

    A property of the code, not of a run, so it answers before anything has
    been inspected -- the structure is the thing you want to look at first.
    """
    # ``steppable`` is the subset a breakpoint can name: the real nodes, without
    # LangGraph's own start and end markers.
    return {**graph_shape(), "steppable": list(NODES)}


@router.get("/runs")
def get_runs() -> Dict[str, Any]:
    """Every run, most recently touched first, labelled by its files."""
    return {"runs": list_runs()}


@router.delete("/runs/{run_id}")
def remove_run(run_id: str) -> Dict[str, Any]:
    """Delete a run and everything in it.

    Trying things out leaves workspaces behind, and a list full of abandoned
    ones is worse than useless. A run in flight is refused rather than pulled
    out from under its worker.
    """
    paths = _require_run(run_id)
    if _live_channel(run_id) is not None:
        raise HTTPException(status_code=409, detail="this run is in flight; stop it first")

    delete_run(paths)
    with _channels_lock:
        _channels.pop(run_id, None)
    return {"deleted": run_id}


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
        store.clear_index()
        # Writes the knowledge graph beside the index too -- it is derived from
        # exactly this and goes stale with exactly this.
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
        store.drop_findings_in_file(path)
    finally:
        store.close()
    return {"deleted": path, "index": _reindex(paths), "files": sorted(iter_all_files(paths))}


@router.get("/runs/{run_id}")
def run_detail(run_id: str) -> Dict[str, Any]:
    """One run, described the way the list describes them.

    The trace view shows a single run rather than a list, so this is where its
    heading comes from: which files, what status, when it last did anything.
    """
    return describe_run(_require_run(run_id))


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
def run_checkpoints(run_id: str, full: bool = False) -> Dict[str, Any]:
    """This run's state after each super-step, oldest first.

    The trace says what was called; this says what the graph *knew* at each
    step -- what was still queued, what the last node wrote, where it would go
    next. One thread per run, so this is only ever this run's history.

    ``?full=true`` returns the bulky fields rather than counting them, which is
    what the thread panel asks for when a step is expanded.
    """
    paths = _require_run(run_id)
    steps = paths.checkpoints(full=full)
    return {"run_id": run_id, "checkpoints": steps, "count": len(steps)}


@router.get("/runs/{run_id}/state")
def run_state(run_id: str, checkpoint_id: str | None = None) -> Dict[str, Any]:
    """One checkpoint's state in full.

    The history summarises the bulky fields, which is right for a timeline and
    wrong for an editor: a count cannot be edited back into a list. Defaults to
    the latest checkpoint, which is where a stopped run is sitting.
    """
    paths = _require_run(run_id)
    state = paths.state(checkpoint_id)
    if state is None:
        raise HTTPException(status_code=404, detail="this run has no state at that point")
    return {"run_id": run_id, **state}


@router.post("/runs/{run_id}/state")
def set_run_state(run_id: str, request: StateRequest) -> Dict[str, Any]:
    """Write state over a checkpoint, branching the run there.

    Nothing is overwritten: the write lands as a child of the checkpoint it was
    made against, so the course already recorded survives being second-guessed
    and both lines show up in the history.
    """
    paths = _require_run(run_id)
    if request.as_node is not None and request.as_node not in NODES:
        raise HTTPException(status_code=400, detail=f"unknown node: {request.as_node}")
    if not paths.checkpoint_db.exists():
        raise HTTPException(status_code=409, detail="this run has no history to write over")

    try:
        checkpoint_id = paths.set_state(request.values, request.checkpoint_id, request.as_node)
    except ValueError as err:
        # LangGraph refuses a write it cannot attribute to a node.
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"run_id": run_id, "checkpoint_id": checkpoint_id}


@router.get("/runs/{run_id}/graph")
def run_knowledge_graph(run_id: str) -> Dict[str, Any]:
    """The tree as a graph: units, what connects them, and the subsystems.

    A property of the code, not of any inspection, so it answers for a run that
    has never been inspected. Built at index time; derived on the spot for a run
    indexed before this existed.
    """
    paths = _require_run(run_id)
    loaded = read_graph(paths.knowledge_graph)
    if loaded is None:
        if not paths.index_db.exists():
            raise HTTPException(status_code=404, detail="this run has not been indexed")
        store = paths.store()
        try:
            write_graph(store, paths.source, paths.knowledge_graph)
        finally:
            store.close()
        loaded = read_graph(paths.knowledge_graph)
    if loaded is None:
        raise HTTPException(status_code=500, detail="the knowledge graph could not be built")

    graph, communities = loaded
    return {"run_id": run_id, **knowledge_json(graph, communities)}


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


class ReplayRequest(BaseModel):
    """Run one recorded model call again, with the prompt changed."""

    #: Defaults to what the span recorded, so an unedited replay is a re-run of
    #: exactly what happened.
    system: Optional[str] = None
    user: Optional[str] = None


#: Which schema a step's call is guided into. `gather` is the odd one out: it is
#: a tool-calling loop returning prose, not a structured object.
#: What guided decoding constrained each kind of call to, so a replay is
#: constrained the same way. Every specialist produces a ChunkAnalysis -- the
#: lens is in the prompt, not in the shape of the answer.
_REPLAY_SCHEMAS = {
    "triage": "Triage",
    "verify": "Verdict",
    **{lens_prompt(lens): "ChunkAnalysis" for lens in LENSES},
}


def _recorded_messages(span: Any) -> tuple[str, str]:
    """The system and user text of a recorded model call."""
    inputs = span.inputs if isinstance(span.inputs, dict) else {}
    messages = inputs.get("messages")
    if isinstance(messages, list):
        system = next((m.get("content", "") for m in messages if m.get("role") == "system"), "")
        user = next((m.get("content", "") for m in messages if m.get("role") in ("human", "user")), "")
        return str(system), str(user)
    prompts = inputs.get("prompts")
    if isinstance(prompts, list) and prompts:
        return "", str(prompts[0])
    return "", ""


@router.post("/runs/{run_id}/spans/{span_id}/replay")
def replay_span(run_id: str, span_id: str, request: ReplayRequest | None = None) -> Dict[str, Any]:
    """Call the model again for one span, optionally with an edited prompt.

    A side experiment, deliberately: it writes nothing to the run, the trace or
    the report. The point is to see what a changed prompt would have produced
    for an input that really occurred, and to be able to try that ten times
    without turning the recorded run into a scratchpad. Changing the run's
    course is what the checkpoint fork is for.
    """
    paths = _require_run(run_id)
    options = request or ReplayRequest()

    if not paths.trace_db.exists():
        raise HTTPException(status_code=404, detail="this run has no trace")

    spans = paths.spans()
    try:
        span = next((s for s in spans.spans() if s.id == span_id), None)
    finally:
        spans.close()

    if span is None:
        raise HTTPException(status_code=404, detail=f"unknown span: {span_id}")
    if span.kind != "llm":
        raise HTTPException(status_code=400, detail="only a model call can be replayed")

    recorded_system, recorded_user = _recorded_messages(span)
    system = options.system if options.system is not None else recorded_system
    user = options.user if options.user is not None else recorded_user
    if not user.strip():
        raise HTTPException(status_code=400, detail="this span recorded no prompt to replay")

    config = AgentConfig()
    try:
        config.require_model()
    except RuntimeError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err

    step = str(span.meta.get("step") or "")
    schema = _REPLAY_SCHEMAS.get(step)

    started = time.monotonic()
    caller = StructuredCaller(config)
    if schema is None:
        # No schema for this step, so the reply is taken as text. Tools are not
        # offered: a replay must not touch the filesystem or the sandbox.
        result: Any = caller.llm.invoke([("system", system), ("human", user)]).content
    else:
        from agent import schema as wire

        produced = caller.call(getattr(wire, schema), system, user)
        result = produced.model_dump() if produced is not None else None

    return {
        "run_id": run_id,
        "span_id": span_id,
        "step": step or None,
        "schema": schema,
        "output": result,
        "latency_ms": int((time.monotonic() - started) * 1000),
        # So the UI can say what it is comparing against without a second read.
        "recorded": {"system": recorded_system, "user": recorded_user, "output": span.outputs},
        "edited": system != recorded_system or user != recorded_user,
    }


@router.get("/prompts")
def list_prompts() -> Dict[str, Any]:
    """The system prompts, their shipped defaults, and any tuning applied."""
    return {"prompts": prompt_store.describe(AgentConfig().prompts_file)}


class PromptRequest(BaseModel):
    text: str


@router.put("/prompts/{name}")
def put_prompt(name: str, request: PromptRequest) -> Dict[str, Any]:
    """Adopt a tuned prompt. Every later run uses it until it is cleared."""
    path = AgentConfig().prompts_file
    try:
        prompt_store.save(path, name, request.text)
    except prompt_store.UnknownPrompt as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"prompts": prompt_store.describe(path)}


@router.delete("/prompts/{name}")
def delete_prompt(name: str) -> Dict[str, Any]:
    """Go back to the prompt the code ships with."""
    path = AgentConfig().prompts_file
    try:
        prompt_store.clear(path, name)
    except prompt_store.UnknownPrompt as err:
        raise HTTPException(status_code=404, detail=str(err)) from err
    return {"prompts": prompt_store.describe(path)}


@router.get("/runs/{run_id}/input")
def run_input(run_id: str) -> Dict[str, Any]:
    """The state a fresh run would begin from.

    The studio shows this as the run's input *before* there is a run, so it
    cannot come from a checkpoint. Computed from the index instead, which is
    where the starting queue comes from anyway -- and it is a pure function of
    it, so this costs a read rather than a session.
    """
    paths = _require_run(run_id)
    store = paths.store()
    try:
        order = store.order()
    finally:
        store.close()

    stats = paths.read_meta().get("index", {})
    return {"run_id": run_id, "values": dict(initial_state(order, len(order), stats))}


@router.get("/runs/{run_id}/files")
def run_files(run_id: str) -> Dict[str, Any]:
    """Every file in the run.

    The run record deliberately carries at most ``LABEL_FILES`` names, because
    it is a label -- but that left no way at all to list a run's tree. Reopening
    a shared ``?run=`` link gave the editor an empty explorer, and the client
    had to reconstruct the list from whichever mutation it happened to perform
    last. Same helper the upload and write endpoints already return.
    """
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


def _inspect_worker(paths: RunPaths, channel: RunChannel, order: WorkOrder) -> None:
    """Drive one inspection on a worker thread, publishing progress.

    The loop exists for breakpoints: the graph returns when it stops at one, and
    the run is not over -- it is waiting. The session stays open across the wait
    so the MCP subprocess and the chunk store are still there when it carries on.
    """
    config = AgentConfig()
    store = paths.store()
    if order.fresh:
        # Two attempts interleaved in one history read as one incoherent run.
        paths.reset_debug()
    spans = paths.spans()

    def emit(event: str, payload: dict[str, Any]) -> None:
        channel.publish({"event": event, "data": payload})

    session: InspectionSession | None = None
    try:
        config.require_model()
        if order.force:
            store.clear_results()

        index_stats = paths.read_meta().get("index", {})
        paths.set_status(STATUS_INSPECTING)
        emit("run_started", {"run_id": paths.run_id, **index_stats})

        session = InspectionSession(
            run_id=paths.run_id,
            root=paths.source,
            store=store,
            config=config,
            emit=emit,
            index_stats=index_stats,
            spans=spans,
            checkpoints=paths.checkpoint_db,
            breakpoints=order.breakpoints,
            breakpoints_after=order.breakpoints_after,
        )

        if order.fresh:
            session.start(values=order.values)
        else:
            session.resume(values=order.resume_values, checkpoint_id=order.resume_from)

        aborted = False
        while session.interrupted and not aborted:
            paths.set_status(STATUS_INTERRUPTED)
            emit(
                "run_interrupted",
                {
                    "run_id": paths.run_id,
                    "next": session.next_nodes,
                    "checkpoint_id": session.checkpoint_id,
                },
            )
            command = _await_command(channel)
            if command.get("action") == "abort":
                aborted = True
                break
            paths.set_status(STATUS_INSPECTING)
            emit("run_resumed", {"run_id": paths.run_id})
            try:
                session.resume(values=command.get("values"), checkpoint_id=command.get("checkpoint_id"))
            except ParallelStep as err:
                # An edit that cannot be attributed to a node. Reported and the
                # run left where it was, rather than torn down: the run is fine,
                # the question was not, and the answer is to ask a different one.
                emit("resume_refused", {"run_id": paths.run_id, "error": str(err)})
                continue

        report = session.report()
        paths.save_report(report)
        paths.set_status(STATUS_DONE, findings=len(report.findings))
        emit(
            "run_finished",
            {"run_id": paths.run_id, "findings": len(report.findings), "aborted": aborted},
        )
    except Exception as err:  # noqa: BLE001 - the failure is reported, not raised into the loop
        log.exception("inspection failed for run %s", paths.run_id)
        channel.error = str(err)
        paths.set_status(STATUS_FAILED, error=str(err))
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


def _spawn(paths: RunPaths, order: WorkOrder) -> RunChannel:
    """Put a worker on the run, reusing the channel anyone is already watching."""
    channel = _channel(paths.run_id)
    channel.reclaim()
    threading.Thread(
        target=_inspect_worker,
        args=(paths, channel, order),
        name=f"inspect-{paths.run_id}",
        daemon=True,
    ).start()
    return channel


def _live_channel(run_id: str) -> Optional[RunChannel]:
    """The run's channel if a worker is still on it.

    Watching is not running: the studio opens the stream when a run is selected,
    long before anyone presses start, and that must not read as in flight.
    """
    with _channels_lock:
        channel = _channels.get(run_id)
    if channel is None or not channel.claimed or channel.finished.is_set():
        return None
    return channel


@router.post("/runs/{run_id}/inspect")
def start_inspection(run_id: str, request: InspectRequest | None = None) -> Dict[str, Any]:
    """Start an inspection. Returns immediately; watch ``/events``."""
    paths = _require_run(run_id)
    options = request or InspectRequest()
    breakpoints = _validate_breakpoints(options.breakpoints)
    after = _validate_breakpoints(options.breakpoints_after)

    if _live_channel(run_id) is not None:
        return {"run_id": run_id, "status": STATUS_INSPECTING, "already_running": True}

    _spawn(
        paths,
        WorkOrder(
            breakpoints=breakpoints,
            breakpoints_after=after,
            force=options.force,
            values=options.values,
        ),
    )
    return {
        "run_id": run_id,
        "status": STATUS_INSPECTING,
        "already_running": False,
        "breakpoints": breakpoints,
        "breakpoints_after": after,
    }


@router.post("/runs/{run_id}/resume")
def resume_inspection(run_id: str, request: ResumeRequest | None = None) -> Dict[str, Any]:
    """Let a stopped run carry on, optionally with the state changed.

    Two ways in. A run still paused at a breakpoint is steered by handing the
    waiting worker its answer, which keeps the tools it already has open. A run
    whose worker is gone -- the server restarted, or it finished -- is picked up
    again from its checkpoints by a new worker.
    """
    paths = _require_run(run_id)
    options = request or ResumeRequest()
    if options.action not in ("resume", "abort"):
        raise HTTPException(status_code=400, detail=f"unknown action: {options.action}")

    channel = _live_channel(run_id)
    if channel is not None:
        if not channel.waiting.is_set():
            raise HTTPException(status_code=409, detail="this run is not stopped at a breakpoint")
        channel.commands.put(
            {"action": options.action, "values": options.values, "checkpoint_id": options.checkpoint_id}
        )
        return {"run_id": run_id, "resumed": options.action == "resume", "worker": "existing"}

    if options.action == "abort":
        raise HTTPException(status_code=409, detail="no run is in flight")
    if not paths.checkpoint_db.exists():
        raise HTTPException(status_code=409, detail="this run has no history to resume from")

    _spawn(
        paths,
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
    return {"run_id": run_id, "resumed": True, "worker": "new"}


@router.get("/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """Server-sent events for an in-flight inspection.

    SSE rather than websockets: the traffic is one-way and this rides on the
    existing HTTP server with no extra protocol handling.
    """
    _require_run(run_id)
    channel = _channel(run_id)

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
