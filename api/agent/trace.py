"""What one run actually did: its call tree, its knowledge graph, and the
conversations it had.

Read-only. Editing a run's state mid-flight and replaying one recorded call
belonged to the studio, which 검사 no longer has -- what remains is what a
finding's 판단 과정 is drawn from.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from agent.knowledge import read_graph, write_graph
from graphify import to_json as knowledge_json

from .deps import RunDep

log = logging.getLogger(__name__)
router = APIRouter()


@router.get("/runs/{run_id}/spans")
def run_spans(run: RunDep) -> Dict[str, Any]:
    """The call tree of this run's last inspection.

    Recorded locally, so the debug view works with no LangSmith account, no key
    and no egress -- and can be shown to a user, which the hosted view cannot
    (it serves ``frame-ancestors 'self'`` and needs a login besides).

    Readable mid-run: the store is WAL, so this returns what has landed so far
    with unfinished spans still marked ``running``.
    """
    spans = run.spans()
    try:
        rows = [span.as_dict() for span in spans.spans()]
    finally:
        spans.close()
    return {"run_id": run.run_id, "spans": rows, "summary": _span_summary(rows)}


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


@router.get("/runs/{run_id}/graph")
def run_knowledge_graph(run: RunDep) -> Dict[str, Any]:
    """The tree as a graph: units, what connects them, and the subsystems.

    A property of the code, not of any inspection, so it answers for a run that
    has never been inspected. Built at index time; derived on the spot for a run
    indexed before this existed.
    """
    loaded = read_graph(run.run_id)
    if loaded is None:
        store = run.store()
        try:
            if not store.order():
                raise HTTPException(status_code=404, detail="this run has not been indexed")
            write_graph(store)
        finally:
            store.close()
        loaded = read_graph(run.run_id)
    if loaded is None:
        raise HTTPException(status_code=500, detail="the knowledge graph could not be built")

    graph, communities = loaded
    return {"run_id": run.run_id, **knowledge_json(graph, communities)}


@router.get("/runs/{run_id}/thread")
def run_thread(run: RunDep) -> Dict[str, Any]:
    """The run as conversations -- one per chunk, in the order they happened.

    A span tree shows the machinery. This shows the exchange: what the agent was
    asked, what it answered, which tools it reached for and what came back.
    """
    spans = run.spans()
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

    return {"run_id": run.run_id, "threads": list(threads.values())}


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
        # graph is a comparison rather than a guess at the span's name: a span is
        # named `{step}:{subject}`, so `lens:memory` in the `memory` node is
        # called neither of those things.
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
