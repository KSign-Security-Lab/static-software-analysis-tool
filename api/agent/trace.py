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
    spans = run.spans()
    try:
        rows = [span.as_dict() for span in spans.spans()]
    finally:
        spans.close()
    return {"run_id": run.run_id, "spans": rows, "summary": _span_summary(rows)}


def _span_summary(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
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
    inputs = span.inputs if isinstance(span.inputs, dict) else {}
    outputs = span.outputs if isinstance(span.outputs, dict) else {}
    messages = inputs.get("messages")
    if not isinstance(messages, list):
        messages = [{"role": "human", "content": text} for text in inputs.get("prompts", [])]

    return {
        "id": span.id,
        "step": span.meta.get("step") or span.name,
        "name": span.name,
        "node": span.meta.get("langgraph_node"),
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
