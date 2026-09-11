from __future__ import annotations

from typing import Any, Mapping, Sequence, cast

from langgraph.graph import END, START, StateGraph

from ..config import AgentConfig
from ..index.store import ChunkStore
from ..llm import StructuredCaller
from ..mcp.client import ToolSession
from ..schema import LENSES, Report
from ..trace import SpanStore
from .nodes import NodeDeps, ProgressSink, claims, dispatch, has_work, make_nodes, scouts, specialists
from .state import ChunkState, InspectionState

NODE_VISITS_PER_CHUNK = 10
RECURSION_HEADROOM = 20
CHUNK_NODES = ("triage", "scout", *LENSES, "skip", "locate", "gather", "verify", "reduce")
PARENT_NODES = ("plan", "replan", "context")
# The node names a breakpoint may name, and the shape the API publishes: the
# subgraph is a container, not a step, so it is not one of them.
NODES = (*PARENT_NODES, *CHUNK_NODES)
CONTAINER = "inspect"


def build_chunk_graph(deps: NodeDeps, breakpoints: Sequence[str] = (), breakpoints_after: Sequence[str] = ()) -> Any:
    nodes = make_nodes(deps)
    # No output_schema: it filters what the routers see, not just what leaves.
    # The parent drops the inner channels anyway -- it no longer declares them.
    graph = StateGraph(ChunkState)

    graph.add_node("triage", nodes["triage"])
    graph.add_node("scout", nodes["scout"])
    for lens in LENSES:
        graph.add_node(lens, nodes[lens])
    graph.add_node("skip", nodes["skip"])
    graph.add_node("locate", nodes["locate"])
    graph.add_node("gather", nodes["gather"], destinations=("verify",))
    graph.add_node("verify", nodes["verify"])
    graph.add_node("reduce", nodes["reduce"])

    graph.add_edge(START, "triage" if deps.config.triage else "scout")
    graph.add_conditional_edges("triage", scouts, ["scout"])
    graph.add_conditional_edges("scout", specialists(deps.config), [*LENSES, "skip"])
    for source in (*LENSES, "skip"):
        graph.add_edge(source, "locate")
    graph.add_conditional_edges("locate", claims, ["gather", "reduce"])
    graph.add_edge("verify", "reduce")
    graph.add_edge("reduce", END)
    return graph.compile(interrupt_before=list(breakpoints), interrupt_after=list(breakpoints_after))


def build_graph(
    deps: NodeDeps,
    checkpointer: Any = None,
    breakpoints: Sequence[str] = (),
    breakpoints_after: Sequence[str] = (),
) -> Any:
    unknown = sorted((set(breakpoints) | set(breakpoints_after)) - set(NODES))
    if unknown:
        raise ValueError(f"unknown node(s) for a breakpoint: {', '.join(unknown)}")

    inner = set(CHUNK_NODES)
    nodes = make_nodes(deps)
    graph = StateGraph(InspectionState)

    graph.add_node("plan", nodes["plan"])
    graph.add_node("context", nodes["context"])
    graph.add_node(
        CONTAINER,
        build_chunk_graph(
            deps,
            [name for name in breakpoints if name in inner],
            [name for name in breakpoints_after if name in inner],
        ),
        destinations=("plan",),
    )

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", has_work, {"context": "context", "done": END})
    graph.add_conditional_edges("context", dispatch(deps.config), [CONTAINER])
    if deps.config.advisory_planning:
        graph.add_node("replan", nodes["replan"])
        graph.add_edge(CONTAINER, "replan")
        graph.add_edge("replan", "plan")
    else:
        graph.add_edge(CONTAINER, "plan")
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=[name for name in breakpoints if name not in inner],
        interrupt_after=[name for name in breakpoints_after if name not in inner],
    )


def hollow_deps() -> NodeDeps:
    return NodeDeps(store=cast(Any, None), config=AgentConfig(), caller=cast(Any, None), files={})


def _flat(name: str) -> str:
    return name.split(":", 1)[1] if name.startswith(f"{CONTAINER}:") else name


def graph_shape() -> dict[str, Any]:
    shape = build_graph(hollow_deps()).get_graph(xray=True)
    return {
        "nodes": [_flat(name) for name in shape.nodes],
        "edges": [
            {"source": _flat(edge.source), "target": _flat(edge.target), "conditional": bool(edge.conditional)}
            for edge in shape.edges
        ],
        "mermaid": shape.draw_mermaid(),
    }


def run_inspection(
    *,
    run_id: str,
    files: Mapping[str, str],
    store: ChunkStore,
    config: AgentConfig,
    caller: StructuredCaller | None = None,
    emit: ProgressSink | None = None,
    index_stats: dict[str, int] | None = None,
    tools: ToolSession | None = None,
    spans: SpanStore | None = None,
    checkpoints: bool = False,
    warm: bool = True,
) -> Report:
    from .session import InspectionSession

    with InspectionSession(
        run_id=run_id,
        files=files,
        store=store,
        config=config,
        caller=caller,
        emit=emit,
        index_stats=index_stats,
        tools=tools,
        spans=spans,
        checkpoints=checkpoints,
    ) as session:
        session.start(warm=warm)
        return session.report()
