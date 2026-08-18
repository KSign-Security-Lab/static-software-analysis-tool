"""Wire the nodes into a graph and run it.

The loop is::

    plan -> context -> triage -> scout -> {memory, injection, access, logic}
         -> locate -> gather -> verify -> reduce -> plan

exiting when ``plan`` finds no unvisited chunk. Five of those arrows fan out:
one triage per chunk in the wave, one scout per chunk worth analysing, one
specialist per lens that chunk earned *times* each stretch scout picked out, one
investigation per finding, and the verifier that investigation hands its claim
to. Everything joins again at ``locate`` and ``reduce``, which is where order is
restored.

Control flow is deterministic: the model decides what a chunk *contains* and
which specialists it deserves, never which chunk comes next or where the graph
goes. That is what makes two runs over the same tree comparable.

LangGraph earns its place here for the state machine, the fan-out and its
recursion accounting, not for agentic routing.
"""

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
from .state import InspectionState

#: What one chunk costs in node visits, on the longest road through the graph.
#: The limit is generous so a large upload is bounded by the queue rather than
#: by LangGraph, and it is computed from the work rather than guessed. A wave
#: pays this once for the whole wave, so the real bound is looser still.
NODE_VISITS_PER_CHUNK = 10
RECURSION_HEADROOM = 20

#: The graph's nodes, named once. A breakpoint is checked against this, and the
#: API answers with it, so neither has to compile a graph to find out. Every
#: lens is registered whether or not this run uses it, so the drawing of the
#: agent is the same drawing however the run is configured.
#: `replan` is here whether or not this run uses it, for the same reason every
#: lens is: a breakpoint names a node, and the drawing of the agent should not
#: change shape with a flag.
NODES = ("plan", "replan", "context", "triage", "scout", *LENSES, "skip", "locate", "gather", "verify", "reduce")


def build_graph(
    deps: NodeDeps,
    checkpointer: Any = None,
    breakpoints: Sequence[str] = (),
    breakpoints_after: Sequence[str] = (),
) -> Any:
    """Compile the inspection graph.

    With a ``checkpointer`` every super-step's state is written to disk, which
    is what makes a finished run steppable after the fact and an interrupted
    one resumable.

    ``breakpoints`` names nodes to stop *before* and ``breakpoints_after`` names
    nodes to stop *after* -- before it runs, or once it has written. Stopping is
    implemented by the checkpointer -- the graph saves its state and returns, and
    resuming replays from there -- so it needs one, and an unknown node name is
    refused here rather than silently never firing.
    """
    unknown = sorted((set(breakpoints) | set(breakpoints_after)) - set(NODES))
    if unknown:
        raise ValueError(f"unknown node(s) for a breakpoint: {', '.join(unknown)}")

    nodes = make_nodes(deps)
    graph = StateGraph(InspectionState)

    # Registered one by one rather than in a loop: the loop hid which nodes
    # exist, and `add_node` cannot infer the state type through a dict. The
    # specialists are the exception -- they are a set by definition, and naming
    # them here as well as in `schema.LENSES` would be one place to forget.
    graph.add_node("plan", nodes["plan"])
    graph.add_node("context", nodes["context"])
    graph.add_node("triage", nodes["triage"])
    graph.add_node("scout", nodes["scout"])
    for lens in LENSES:
        graph.add_node(lens, nodes[lens])
    graph.add_node("skip", nodes["skip"])
    graph.add_node("locate", nodes["locate"])
    # `destinations` because `gather` routes itself: it returns a `Command`
    # carrying a `Send`, and a `Send` decided inside a node is invisible to
    # `get_graph()` unless the node declares where it can go. Same reason the
    # conditional edges below list their targets -- an undrawn edge is a lie.
    graph.add_node("gather", nodes["gather"], destinations=("verify",))
    graph.add_node("verify", nodes["verify"])
    graph.add_node("reduce", nodes["reduce"])

    graph.add_edge(START, "plan")
    graph.add_conditional_edges("plan", has_work, {"context": "context", "done": END})
    # The target lists are for the drawing as much as the routing: a `Send` is
    # invisible to `get_graph()` unless the edge says where it can go. With
    # screening on, `context` only ever reaches the specialists through
    # `triage`, and saying so keeps the drawing honest rather than exhaustive.
    after_context = ["triage", "skip"] if deps.config.triage else ["scout", "skip"]
    graph.add_conditional_edges("context", dispatch(deps.config), after_context)
    graph.add_conditional_edges("triage", scouts, ["scout"])
    graph.add_conditional_edges("scout", specialists(deps.config), [*LENSES, "skip"])
    # Everything the specialists layer contains joins here, and only here. That
    # is what makes `locate` run once per wave rather than once per route into
    # it -- see `nodes.skip`.
    for source in (*LENSES, "skip"):
        graph.add_edge(source, "locate")
    graph.add_conditional_edges("locate", claims, ["gather", "reduce"])
    graph.add_edge("verify", "reduce")
    # Advisory planning puts one node between the end of a wave and the start
    # of the next. It writes events and returns no state, so `computed` mode
    # is this edge and nothing else -- the node is not registered at all, and
    # a run cannot pay for a planner it did not ask for.
    if deps.config.advisory_planning:
        graph.add_node("replan", nodes["replan"])
        graph.add_edge("reduce", "replan")
        graph.add_edge("replan", "plan")
    else:
        graph.add_edge("reduce", "plan")
    return graph.compile(
        checkpointer=checkpointer,
        interrupt_before=list(breakpoints),
        interrupt_after=list(breakpoints_after),
    )


def hollow_deps() -> NodeDeps:
    """Dependencies for a graph that will be compiled but not run.

    The nodes only close over what they are given; nothing is touched until a
    node executes. That is enough to read the graph's shape, or to reopen it
    over a saver purely to replay history.
    """
    return NodeDeps(store=cast(Any, None), config=AgentConfig(), caller=cast(Any, None), files={})


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
    files: Mapping[str, str],
    store: ChunkStore,
    config: AgentConfig,
    caller: StructuredCaller | None = None,
    emit: ProgressSink | None = None,
    index_stats: dict[str, int] | None = None,
    tools: ToolSession | None = None,
    spans: SpanStore | None = None,
    #: Whether to keep state snapshots. Was the path to a per-run file.
    checkpoints: bool = False,
    #: Whether earlier runs' results may answer for a chunk. Off is `force`.
    warm: bool = True,
) -> Report:
    """Inspect an already-indexed tree, start to finish, and return the report.

    The one-shot form: open everything, run to the end, close everything. That
    is what the CLI wants. A run that has to stop and be steered wants
    :class:`~agent.graph.session.InspectionSession`, which this is built on.
    """
    # Imported here because the session is built on this module's graph, and at
    # module scope the two would import each other.
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
