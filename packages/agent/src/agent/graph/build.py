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
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from ..config import AgentConfig
from ..index.store import ChunkStore
from ..llm import StructuredCaller
from ..mcp.client import VERIFY_TOOLS, ToolSession, open_session
from ..schema import Finding, Report, RunStats
from ..trace import SpanRecorder, SpanStore
from ..tracing import apply_default_project
from .checkpoints import checkpoint_saver
from .nodes import NodeDeps, ProgressSink, has_work, make_nodes
from .state import InspectionState, initial_state

#: One chunk costs five node visits. The limit is generous so a large upload is
#: bounded by the queue rather than by LangGraph, and it is computed from the
#: work rather than guessed.
NODE_VISITS_PER_CHUNK = 5
RECURSION_HEADROOM = 20


def build_graph(deps: NodeDeps, checkpointer: Any = None) -> Any:
    """Compile the inspection graph.

    With a ``checkpointer`` every super-step's state is written to disk, which
    is what makes a finished run steppable after the fact and an interrupted
    one resumable.
    """
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
    return graph.compile(checkpointer=checkpointer)


def hollow_deps() -> NodeDeps:
    """Dependencies for a graph that will be compiled but not run.

    The nodes only close over what they are given; nothing is touched until a
    node executes. That is enough to read the graph's shape, or to reopen it
    over a saver purely to replay history.
    """
    return NodeDeps(store=cast(Any, None), config=AgentConfig(), caller=cast(Any, None), root=Path())


def graph_shape() -> dict[str, Any]:
    """Nodes and edges of the inspection graph, with no dependencies attached.

    The structure is a property of the code, not of any run, so this answers
    without a store, a model or a workspace -- which is what lets the UI draw
    the graph before anything has been inspected.
    """
    shape = build_graph(hollow_deps()).get_graph()
    return {
        "nodes": [name for name in shape.nodes],
        "edges": [
            {"source": edge.source, "target": edge.target, "conditional": bool(edge.conditional)}
            for edge in shape.edges
        ],
        "mermaid": shape.draw_mermaid(),
    }


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
    checkpoints: Path | None = None,
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

    # One thread per run, so a run's history is its own and stepping through it
    # afterwards shows that run's states and nobody else's.
    saver = checkpoint_saver(checkpoints) if checkpoints is not None else None
    invocation: dict[str, Any] = {
        "recursion_limit": len(order) * NODE_VISITS_PER_CHUNK + RECURSION_HEADROOM,
        "callbacks": [recorder] if recorder is not None else None,
    }
    if saver is not None:
        invocation["configurable"] = {"thread_id": run_id}

    try:
        app = build_graph(deps, checkpointer=saver)
        final: dict[str, Any] = app.invoke(state, config=invocation)
    finally:
        if owned_session is not None:
            owned_session.close()
        if saver is not None:
            saver.conn.close()

    stats = RunStats(**{k: v for k, v in final.get("stats", {}).items() if k in RunStats.model_fields})
    findings = [Finding.model_validate(payload) for payload in store.findings()]
    report = Report(run_id=run_id, findings=findings, stats=stats)
    report.findings = report.sorted_findings()
    return report
