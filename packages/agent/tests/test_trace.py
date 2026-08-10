"""Local tracing: the store, and the callback handler that fills it."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from agent.trace import SpanRecorder, SpanStore
from agent.trace.store import MAX_PAYLOAD, clip


@pytest.fixture
def store(tmp_path: Path) -> SpanStore:
    span_store = SpanStore(tmp_path / "trace.db")
    yield span_store
    span_store.close()


def test_clip_bounds_a_large_payload() -> None:
    clipped = clip({"body": "x" * (MAX_PAYLOAD * 2)})
    assert clipped is not None
    assert len(clipped) < MAX_PAYLOAD * 2
    assert "_truncated" in clipped


def test_clip_falls_back_to_str_for_unserialisable() -> None:
    assert clip(object()) is not None


def test_start_and_finish_round_trip(store: SpanStore) -> None:
    store.start(span_id="a", parent_id=None, name="analyse", kind="chain", started_at=100.0)
    store.finish(span_id="a", ended_at=100.5, outputs={"ok": True}, tokens=12)

    (span,) = store.spans()
    assert span.status == "ok"
    assert span.latency_ms == 500
    assert span.tokens == 12
    assert span.outputs == {"ok": True}


def test_an_unfinished_span_is_still_visible(store: SpanStore) -> None:
    store.start(span_id="a", parent_id=None, name="analyse", kind="chain", started_at=100.0)
    (span,) = store.spans()
    assert span.status == "running"
    assert span.latency_ms is None


def test_error_marks_the_span(store: SpanStore) -> None:
    store.start(span_id="a", parent_id=None, name="verify", kind="llm", started_at=1.0)
    store.finish(span_id="a", ended_at=2.0, error="boom")
    (span,) = store.spans()
    assert span.status == "error"
    assert span.error == "boom"


def test_spans_come_back_in_arrival_order(store: SpanStore) -> None:
    for name in ("plan", "context", "analyse"):
        store.start(span_id=name, parent_id=None, name=name, kind="chain", started_at=0.0)
    assert [span.name for span in store.spans()] == ["plan", "context", "analyse"]


def test_clear_empties_and_restarts_numbering(store: SpanStore) -> None:
    store.start(span_id="a", parent_id=None, name="plan", kind="chain", started_at=0.0)
    store.clear()
    assert store.spans() == []
    store.start(span_id="b", parent_id=None, name="plan", kind="chain", started_at=0.0)
    assert store.spans()[0].seq == 1


def test_reopening_continues_the_sequence(tmp_path: Path) -> None:
    first = SpanStore(tmp_path / "trace.db")
    first.start(span_id="a", parent_id=None, name="plan", kind="chain", started_at=0.0)
    first.close()

    second = SpanStore(tmp_path / "trace.db")
    second.start(span_id="b", parent_id=None, name="plan", kind="chain", started_at=0.0)
    assert [span.seq for span in second.spans()] == [1, 2]
    second.close()


# -- recorder --------------------------------------------------------------


def _uuid() -> UUID:
    return uuid4()


def _in_node(name: str) -> dict[str, object]:
    """Metadata as LangGraph reports it. Everything inside a node inherits the
    node's metadata, which is exactly why it cannot be what identifies it."""
    return {"langgraph_node": name, "langgraph_step": 1}


def test_recorder_builds_a_parented_tree(store: SpanStore) -> None:
    recorder = SpanRecorder(store)
    root, child = _uuid(), _uuid()

    recorder.on_chain_start({"name": "LangGraph"}, {}, run_id=root)
    recorder.on_chain_start(
        {}, {}, run_id=child, parent_run_id=root, name="analyse", metadata={"langgraph_node": "analyse"}
    )
    recorder.on_chain_end({}, run_id=child)
    recorder.on_chain_end({}, run_id=root)

    by_id = {span.id: span for span in store.spans()}
    assert by_id[str(child)].parent_id == str(root)
    assert by_id[str(root)].parent_id is None
    assert all(span.status == "ok" for span in by_id.values())


def test_recorder_captures_messages_and_tool_calls(store: SpanStore) -> None:
    recorder = SpanRecorder(store)
    run = _uuid()

    recorder.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[SystemMessage(content="be strict"), HumanMessage(content="check this")]],
        run_id=run,
        metadata={"step": "verify"},
    )
    reply = AIMessage(
        content="",
        tool_calls=[{"name": "read_source", "args": {"path": "fw.c"}, "id": "call-1"}],
    )
    recorder.on_llm_end(
        LLMResult(
            generations=[[ChatGeneration(message=reply)]],
            llm_output={"token_usage": {"total_tokens": 431}},
        ),
        run_id=run,
    )

    (span,) = store.spans()
    assert span.kind == "llm"
    assert span.meta["step"] == "verify"
    assert span.tokens == 431
    assert [message["role"] for message in span.inputs["messages"]] == ["system", "human"]
    assert span.outputs["tool_calls"][0]["name"] == "read_source"


def test_a_tool_is_filed_under_the_model_that_asked_for_it(store: SpanStore) -> None:
    """LangChain reports it under the graph node, because the gathering loop
    runs the tool after the model call has already closed."""
    recorder = SpanRecorder(store)
    node, llm, tool = _uuid(), _uuid(), _uuid()

    recorder.on_chain_start({}, {}, run_id=node, name="verify", metadata=_in_node("verify"))
    recorder.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[HumanMessage(content="go")]],
        run_id=llm,
        parent_run_id=node,
        name="gather:CWE-78",
        metadata=_in_node("verify"),
    )
    recorder.on_llm_end(LLMResult(generations=[[]]), run_id=llm)
    recorder.on_tool_start(
        {"name": "find_callers"},
        '{"symbol": "download"}',
        run_id=tool,
        parent_run_id=node,
        inputs={"symbol": "download"},
    )
    recorder.on_tool_end("fw.c:12", run_id=tool)

    assert [span.name for span in store.spans()] == ["verify", "gather:CWE-78", "find_callers"]
    recorded = next(span for span in store.spans() if span.kind == "tool")
    assert recorded.parent_id == str(llm), "not under the node -- under the call that requested it"
    assert recorded.inputs == {"symbol": "download"}
    assert recorded.outputs == "fw.c:12"
    assert recorded.status == "ok"


def test_framework_plumbing_is_dropped_without_orphaning_its_children(store: SpanStore) -> None:
    """`with_structured_output` wraps the model in a sequence and appends a
    parser. Recording them tripled the tree and said nothing."""
    recorder = SpanRecorder(store)
    node, wrapper, llm, parser = _uuid(), _uuid(), _uuid(), _uuid()

    recorder.on_chain_start({}, {}, run_id=node, name="analyse", metadata=_in_node("analyse"))
    recorder.on_chain_start(
        {}, {}, run_id=wrapper, parent_run_id=node, name="analyse:fw.c", metadata=_in_node("analyse")
    )
    recorder.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[HumanMessage(content="go")]],
        run_id=llm,
        parent_run_id=wrapper,
        metadata=_in_node("analyse"),
    )
    recorder.on_llm_end(LLMResult(generations=[[]]), run_id=llm)
    recorder.on_chain_start(
        {}, {}, run_id=parser, parent_run_id=wrapper, name="RunnableLambda", metadata=_in_node("analyse")
    )
    recorder.on_chain_end({}, run_id=parser)
    recorder.on_chain_end({}, run_id=wrapper)
    recorder.on_chain_end({}, run_id=node)

    names = [span.name for span in store.spans()]
    assert names == ["analyse", "analyse:fw.c"], "the wrapper and the parser are noise"

    # The model kept the wrapper's name -- the run_name lands on the sequence,
    # not on the model, so dropping it blindly would leave a row of ChatOpenAI.
    model = next(span for span in store.spans() if span.kind == "llm")
    assert model.name == "analyse:fw.c"
    assert model.parent_id == str(node), "reattached to the node, not orphaned"


def test_recorder_records_errors(store: SpanStore) -> None:
    recorder = SpanRecorder(store)
    run = _uuid()
    recorder.on_chain_start({"name": "analyse"}, {}, run_id=run)
    recorder.on_chain_error(RuntimeError("the endpoint went away"), run_id=run)

    (span,) = store.spans()
    assert span.status == "error"
    assert "endpoint went away" in (span.error or "")


def test_a_broken_store_does_not_break_the_run(tmp_path: Path) -> None:
    """A tracer that can abort an inspection is worse than no tracer."""
    store = SpanStore(tmp_path / "trace.db")
    store.close()
    recorder = SpanRecorder(store)

    recorder.on_chain_start({"name": "analyse"}, {}, run_id=_uuid())
    recorder.on_chain_end({}, run_id=_uuid())


def test_callbacks_reach_a_model_call_inside_a_graph_node(store: SpanStore) -> None:
    """The load-bearing assumption: the recorder is attached once, at the root,
    and every model call underneath is picked up without threading it through.

    ``call_config`` builds a fresh config for each call, so if it displaced the
    inherited callbacks instead of merging with them, the trace would contain
    the nodes and nothing else -- which is the half that matters.
    """
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langgraph.graph import END, START, StateGraph
    from typing_extensions import TypedDict

    from agent.tracing import call_config

    model = GenericFakeChatModel(messages=iter([AIMessage(content="clean")]))

    class State(TypedDict, total=False):
        answer: str

    def analyse(state: State) -> dict[str, str]:
        reply = model.invoke(
            [HumanMessage(content="inspect this")],
            config=call_config(step="analyse", run_id="r1", symbol="handler", subject="handler"),
        )
        return {"answer": str(reply.content)}

    graph = StateGraph(State)
    graph.add_node("analyse", analyse)
    graph.add_edge(START, "analyse")
    graph.add_edge("analyse", END)
    graph.compile().invoke({}, config={"callbacks": [SpanRecorder(store)]})

    llm = next(span for span in store.spans() if span.kind == "llm")
    assert llm.name == "analyse:handler"
    assert llm.meta["step"] == "analyse"
    assert llm.parent_id is not None, "the model call should hang under the node, not float at the root"
    assert llm.outputs["text"] == ["clean"]


def test_a_tool_stays_with_its_own_model_call_across_threads(store: SpanStore) -> None:
    """With four specialists in flight, one shared "call that is open now" would
    file a tool under whichever model answered last on any thread."""
    import threading

    recorder = SpanRecorder(store)
    started = threading.Barrier(2)
    pairs: dict[str, tuple[UUID, UUID]] = {}

    def branch(lens: str) -> None:
        llm, tool = _uuid(), _uuid()
        pairs[lens] = (llm, tool)
        recorder.on_chat_model_start(
            {"name": "ChatOpenAI"},
            [[HumanMessage(content=lens)]],
            run_id=llm,
            parent_run_id=None,
            name=f"gather:{lens}",
            metadata=_in_node("verify"),
        )
        # Both models are open at once; without thread-local state the second
        # one to start owns every tool call that follows.
        started.wait(timeout=5)
        recorder.on_tool_start({"name": "find_callers"}, "{}", run_id=tool, parent_run_id=None)
        recorder.on_tool_end(lens, run_id=tool)
        recorder.on_llm_end(LLMResult(generations=[[]]), run_id=llm)

    threads = [threading.Thread(target=branch, args=(lens,)) for lens in ("memory", "injection")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    by_id = {span.id: span for span in store.spans()}
    for lens, (llm, tool) in pairs.items():
        assert by_id[str(tool)].parent_id == str(llm), f"{lens}'s tool wandered onto another thread's call"


def test_a_tool_run_on_the_mcp_loop_stays_with_the_call_that_asked(store: SpanStore) -> None:
    """The shape a real run has, and the one thread-local state got wrong.

    ``ToolSession.call`` hands the coroutine to the MCP session's event loop, so
    the tool's callbacks fire on *that* thread while the graph thread waits.
    ``call_soon_threadsafe`` copies the calling context across, which is what a
    ContextVar rides on and what a ``threading.local`` cannot: every tool call
    read an empty field there and was filed under the enclosing node instead,
    leaving the exchange with no tools on it at all.
    """
    import contextvars
    import threading

    recorder = SpanRecorder(store)
    node, llm, tool = _uuid(), _uuid(), _uuid()

    recorder.on_chain_start({}, {}, run_id=node, name="verify", metadata=_in_node("verify"))
    recorder.on_chat_model_start(
        {"name": "ChatOpenAI"},
        [[HumanMessage(content="go")]],
        run_id=llm,
        parent_run_id=node,
        name="gather:CWE-78",
        metadata=_in_node("verify"),
    )

    def on_loop_thread() -> None:
        recorder.on_tool_start({"name": "search_text"}, "{}", run_id=tool, parent_run_id=node)
        recorder.on_tool_end("fw.c:12:strcpy", run_id=tool)

    # Exactly what the loop does with the work it is handed: run it on another
    # thread, in a copy of the caller's context.
    context = contextvars.copy_context()
    worker = threading.Thread(target=context.run, args=(on_loop_thread,))
    worker.start()
    worker.join(timeout=10)

    recorded = next(span for span in store.spans() if span.kind == "tool")
    assert recorded.parent_id == str(llm), "the tool was filed under the node, not the call that asked for it"
