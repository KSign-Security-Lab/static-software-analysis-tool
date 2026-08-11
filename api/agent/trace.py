"""What one run actually did: spans, checkpoints, state, the chat thread, and
replaying a single recorded LLM call.
"""

from __future__ import annotations

import time
from agent.config import AgentConfig
from agent.graph.build import NODES
from agent.schema import LENSES

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agent.knowledge import read_graph, write_graph
from agent.llm import StructuredCaller
from agent.promptstore import lens_prompt
from graphify import to_json as knowledge_json

from .deps import RunDep

log = logging.getLogger(__name__)
router = APIRouter()


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


class StateRequest(BaseModel):
    """Write state over a checkpoint."""

    values: Dict[str, Any]
    checkpoint_id: Optional[str] = None
    #: Whose write this stands in for. Inferred from the checkpoint when absent.
    as_node: Optional[str] = None


@router.get("/runs/{run_id}/spans")
def run_spans(paths: RunDep) -> Dict[str, Any]:
    """The call tree of this run's last inspection.

    Recorded locally, so the debug view works with no LangSmith account, no key
    and no egress -- and can be shown to a user, which the hosted view cannot
    (it serves ``frame-ancestors 'self'`` and needs a login besides).

    Readable mid-run: the store is WAL, so this returns what has landed so far
    with unfinished spans still marked ``running``.
    """
    if not paths.trace_db.exists():
        return {"run_id": paths.run_id, "spans": [], "summary": _span_summary([])}

    spans = paths.spans()
    try:
        rows = [span.as_dict() for span in spans.spans()]
    finally:
        spans.close()
    return {"run_id": paths.run_id, "spans": rows, "summary": _span_summary(rows)}


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
def run_checkpoints(paths: RunDep, full: bool = False) -> Dict[str, Any]:
    """This run's state after each super-step, oldest first.

    The trace says what was called; this says what the graph *knew* at each
    step -- what was still queued, what the last node wrote, where it would go
    next. One thread per run, so this is only ever this run's history.

    ``?full=true`` returns the bulky fields rather than counting them, which is
    what the thread panel asks for when a step is expanded.
    """
    steps = paths.checkpoints(full=full)
    return {"run_id": paths.run_id, "checkpoints": steps, "count": len(steps)}


@router.get("/runs/{run_id}/state")
def run_state(paths: RunDep, checkpoint_id: str | None = None) -> Dict[str, Any]:
    """One checkpoint's state in full.

    The history summarises the bulky fields, which is right for a timeline and
    wrong for an editor: a count cannot be edited back into a list. Defaults to
    the latest checkpoint, which is where a stopped run is sitting.
    """
    state = paths.state(checkpoint_id)
    if state is None:
        raise HTTPException(status_code=404, detail="this run has no state at that point")
    return {"run_id": paths.run_id, **state}


@router.post("/runs/{run_id}/state")
def set_run_state(paths: RunDep, request: StateRequest) -> Dict[str, Any]:
    """Write state over a checkpoint, branching the run there.

    Nothing is overwritten: the write lands as a child of the checkpoint it was
    made against, so the course already recorded survives being second-guessed
    and both lines show up in the history.
    """
    if request.as_node is not None and request.as_node not in NODES:
        raise HTTPException(status_code=400, detail=f"unknown node: {request.as_node}")
    if not paths.checkpoint_db.exists():
        raise HTTPException(status_code=409, detail="this run has no history to write over")

    try:
        checkpoint_id = paths.set_state(request.values, request.checkpoint_id, request.as_node)
    except ValueError as err:
        # LangGraph refuses a write it cannot attribute to a node.
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"run_id": paths.run_id, "checkpoint_id": checkpoint_id}


@router.get("/runs/{run_id}/graph")
def run_knowledge_graph(paths: RunDep) -> Dict[str, Any]:
    """The tree as a graph: units, what connects them, and the subsystems.

    A property of the code, not of any inspection, so it answers for a run that
    has never been inspected. Built at index time; derived on the spot for a run
    indexed before this existed.
    """
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
    return {"run_id": paths.run_id, **knowledge_json(graph, communities)}


@router.get("/runs/{run_id}/thread")
def run_thread(paths: RunDep) -> Dict[str, Any]:
    """The run as conversations -- one per chunk, in the order they happened.

    A span tree shows the machinery. This shows the exchange: what the agent was
    asked, what it answered, which tools it reached for and what came back.
    """
    if not paths.trace_db.exists():
        return {"run_id": paths.run_id, "threads": []}

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

    return {"run_id": paths.run_id, "threads": list(threads.values())}


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
        # Which node made the call, so narrowing the record to one node of the
        # graph is a comparison rather than a guess at the span's name -- `gather`
        # and `verify` are both the `verify` node and neither is called that.
        "node": span.meta.get("langgraph_node"),
        # Which specialist raised the claim this call is about. gather and verify
        # only; it is what makes the hand-off from analysis to verification
        # readable as one chain rather than as unrelated calls that happen to
        # mention the same CWE.
        "raised_by": span.meta.get("lens"),
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
def replay_span(paths: RunDep, span_id: str, request: ReplayRequest | None = None) -> Dict[str, Any]:
    """Call the model again for one span, optionally with an edited prompt.

    A side experiment, deliberately: it writes nothing to the run, the trace or
    the report. The point is to see what a changed prompt would have produced
    for an input that really occurred, and to be able to try that ten times
    without turning the recorded run into a scratchpad. Changing the run's
    course is what the checkpoint fork is for.
    """
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
        "run_id": paths.run_id,
        "span_id": span_id,
        "step": step or None,
        "schema": schema,
        "output": result,
        "latency_ms": int((time.monotonic() - started) * 1000),
        # So the UI can say what it is comparing against without a second read.
        "recorded": {"system": recorded_system, "user": recorded_user, "output": span.outputs},
        "edited": system != recorded_system or user != recorded_user,
    }
