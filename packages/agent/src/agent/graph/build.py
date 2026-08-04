"""Wire the nodes into a graph and run it.

The loop is ``plan -> context -> analyse -> locate -> verify -> plan``, exiting
when ``plan`` finds no unvisited chunk. Control flow is deterministic: the model
decides what a chunk *contains*, never which chunk comes next. That is what
makes two runs over the same tree comparable.

LangGraph earns its place here for the state machine and its recursion
accounting, not for agentic routing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from ..config import AgentConfig
from ..index.store import ChunkStore
from ..llm import StructuredCaller
from ..mcp.client import VERIFY_TOOLS, ToolSession, open_session
from ..schema import Finding, Report, RunStats
from ..trace import SpanRecorder, SpanStore
from ..tracing import apply_default_project
from .nodes import NodeDeps, ProgressSink, has_work, make_nodes
from .state import InspectionState, initial_state

#: One chunk costs five node visits. The limit is generous so a large upload is
#: bounded by the queue rather than by LangGraph, and it is computed from the
#: work rather than guessed.
NODE_VISITS_PER_CHUNK = 5
RECURSION_HEADROOM = 20


def build_graph(deps: NodeDeps) -> Any:
    """Compile the inspection graph."""
    nodes = make_nodes(deps)
    graph = StateGraph(InspectionState)

    # Registered one by one rather than in a loop: the loop hid which nodes
    # exist, and `add_node` cannot infer the state type through a dict.
    graph.add_node("plan", nodes["plan"])
    graph.add_node("context", nodes["context"])
    graph.add_node("analyse", nodes["analyse"])
    graph.add_node("locate", nodes["locate"])
    graph.add_node("verify", nodes["verify"])

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", has_work, {"context": "context", "done": END})
    graph.add_edge("context", "analyse")
    graph.add_edge("analyse", "locate")
    graph.add_edge("locate", "verify")
    graph.add_edge("verify", "plan")
    return graph.compile()


def run_inspection(
    *,
    run_id: str,
    root: Path,
    store: ChunkStore,
    config: AgentConfig,
    caller: StructuredCaller | None = None,
    emit: ProgressSink | None = None,
    index_stats: dict[str, int] | None = None,
    tools: ToolSession | None = None,
    spans: SpanStore | None = None,
) -> Report:
    """Inspect an already-indexed tree and return the report.

    Findings are read back from the store rather than accumulated in graph
    state, so a run that is resumed or partially cached returns everything known
    about the tree -- not only what this invocation happened to produce.
    """
    deps = NodeDeps(
        store=store,
        config=config,
        caller=caller if caller is not None else StructuredCaller(config),
        root=root,
        emit=emit if emit is not None else (lambda event, payload: None),
        run_id=run_id,
        tools=tools,
    )

    # Group traces under one project so a run does not land in LangSmith's
    # `default` alongside everything else on the machine. No-op when tracing is
    # off, and never overrides an explicit LANGSMITH_PROJECT.
    apply_default_project()

    # The agent consumes its own MCP server. Opened for the whole run so the
    # subprocess and its imports are paid for once, not per finding. Absent
    # tools mean verification runs from context, which is a supported mode.
    owned_session: ToolSession | None = None
    if tools is None and config.enable_tools:
        owned_session = open_session(
            run_root=root,
            index_db=store.path,
            sandbox=config.sandbox,
            allowed=VERIFY_TOOLS,
        )
        deps.tools = owned_session

    # Local tracing. Attached at the root so it reaches every node, every model
    # call under them, and every tool call under those -- including the MCP
    # ones, which run on the session's loop thread but inherit this context.
    recorder = SpanRecorder(spans) if spans is not None else None

    order = store.order()
    state = initial_state(order, len(order), index_stats)

    try:
        app = build_graph(deps)
        final: dict[str, Any] = app.invoke(
            state,
            config={
                "recursion_limit": len(order) * NODE_VISITS_PER_CHUNK + RECURSION_HEADROOM,
                "callbacks": [recorder] if recorder is not None else None,
            },
        )
    finally:
        if owned_session is not None:
            owned_session.close()

    stats = RunStats(**{k: v for k, v in final.get("stats", {}).items() if k in RunStats.model_fields})
    findings = [Finding.model_validate(payload) for payload in store.findings()]
    report = Report(run_id=run_id, findings=findings, stats=stats)
    report.findings = report.sorted_findings()
    return report
