"""Local tracing: the store, and the callback handler that fills it."""

from __future__ import annotations

import time
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


def test_recorder_builds_a_parented_tree(store: SpanStore) -> None:
    recorder = SpanRecorder(store)
    root, child = _uuid(), _uuid()

    recorder.on_chain_start({"name": "LangGraph"}, {}, run_id=root)
    recorder.on_chain_start({"name": "analyse"}, {}, run_id=child, parent_run_id=root)
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


def test_recorder_records_an_out_of_band_tool_call_under_the_model(store: SpanStore) -> None:
    recorder = SpanRecorder(store)
    run = _uuid()

    recorder.on_chat_model_start({"name": "ChatOpenAI"}, [[HumanMessage(content="go")]], run_id=run)
    recorder.record_tool(
        name="find_callers",
        args={"symbol": "download"},
        result="fw.c:12",
        started_at=time.time(),
    )

    tool = next(span for span in store.spans() if span.kind == "tool")
    assert tool.parent_id == str(run)
    assert tool.inputs == {"symbol": "download"}
    assert tool.outputs == "fw.c:12"
    assert tool.status == "ok"


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
    recorder.record_tool(name="read_source", args={}, result="", started_at=0.0)


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
