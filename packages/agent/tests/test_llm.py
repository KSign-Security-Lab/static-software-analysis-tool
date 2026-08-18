"""What a structured call does when the model does not finish.

The bug these cover: `call` used to return `None` for both "the model
considered this and found nothing" and "the call died", so callers could not
tell them apart -- and two of them chose to read a dead call as a negative
answer. A run of three files lost the memory analysis of two units and the
patch for a reported finding that way, and reported itself complete.
"""

from __future__ import annotations

from typing import Any

import pytest
from openai import LengthFinishReasonError
from pydantic import BaseModel

from agent.config import AgentConfig
from agent.llm import Outcome, StructuredCaller


class Answer(BaseModel):
    text: str = ""


def _length_error() -> LengthFinishReasonError:
    """The real exception, constructed the way the client raises it."""
    return LengthFinishReasonError.__new__(LengthFinishReasonError)


class FakeLLM:
    """Records what it was bound with, and answers from a script."""

    def __init__(self, script: list[Any]) -> None:
        self.script = script
        self.bound: list[int | None] = []
        self.methods: list[str] = []
        self._headroom: int | None = None

    def bind(self, **kwargs: Any) -> "FakeLLM":
        clone = FakeLLM(self.script)
        clone.bound = self.bound
        clone.methods = self.methods
        clone._headroom = kwargs.get("max_completion_tokens")
        return clone

    def with_structured_output(self, schema: type[BaseModel], method: str = "") -> "FakeLLM":
        self.methods.append(method)
        return self

    def invoke(self, messages: Any, config: Any = None) -> Any:
        self.bound.append(self._headroom)
        nxt = self.script.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


@pytest.fixture
def config() -> AgentConfig:
    cfg = AgentConfig()
    cfg.max_tokens = 4096
    return cfg


def test_a_finished_object_comes_back_as_a_value(config) -> None:
    llm = FakeLLM([Answer(text="ok")])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert outcome.ok
    assert outcome.value.text == "ok"
    assert outcome.reason is None


def test_running_out_of_tokens_retries_with_headroom(config) -> None:
    """Not a fallback to another method: it is not a method problem.

    `json_schema` running out of completion tokens means the model needs more
    room, so `function_calling` fails identically -- which is what used to
    happen, burning a second call to learn nothing.
    """
    llm = FakeLLM([_length_error(), Answer(text="finished")])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert outcome.ok
    assert outcome.value.text == "finished"
    # Twice, and the second at double the ceiling.
    assert llm.bound == [None, 8192]
    # Same method both times; the fallback was never reached.
    assert llm.methods == ["json_schema", "json_schema"]


def test_a_model_too_small_gives_up_and_says_why(config) -> None:
    llm = FakeLLM([_length_error(), _length_error(), _length_error(), _length_error()])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert not outcome.ok
    assert outcome.value is None
    # The reason a caller needs to tell this from a negative answer.
    assert outcome.reason == "length"


def test_a_dead_endpoint_reads_as_transport(config) -> None:
    llm = FakeLLM([RuntimeError("connection refused"), RuntimeError("connection refused")])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert not outcome.ok
    assert outcome.reason == "transport"


def test_a_reply_of_the_wrong_shape_reads_as_refused(config) -> None:
    llm = FakeLLM([{"not": "a model"}, {"not": "a model"}])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert not outcome.ok
    assert outcome.reason == "refused"


def test_an_outcome_never_pretends_a_failure_is_an_answer() -> None:
    """The distinction the whole change exists for."""
    assert Outcome.of(Answer(text="x")).ok
    assert not Outcome.failed("length").ok
    assert Outcome.failed("length").value is None
