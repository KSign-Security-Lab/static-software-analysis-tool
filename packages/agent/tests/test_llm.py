from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from openai import LengthFinishReasonError
from pydantic import BaseModel

from agent.config import AgentConfig
from agent.llm import Outcome, StructuredCaller


class Answer(BaseModel):
    text: str = ""


def _length_error(prompt_tokens: int | None = None) -> LengthFinishReasonError:
    err = LengthFinishReasonError.__new__(LengthFinishReasonError)
    if prompt_tokens is not None:
        err.completion = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=prompt_tokens))
    return err


class FakeLLM:
    def __init__(self, script: list[Any], max_tokens: int = 4096) -> None:
        self.script = script
        self.max_tokens = max_tokens
        self.bound: list[int | None] = []
        self.methods: list[str] = []

    def bind(self, **kwargs: Any) -> "FakeLLM":
        return FakeLLM(self.script, self.max_tokens)._share(self)

    def model_copy(self, update: dict[str, Any] | None = None) -> "FakeLLM":
        clone = FakeLLM(self.script, (update or {}).get("max_tokens", self.max_tokens))
        return clone._share(self)

    def _share(self, other: "FakeLLM") -> "FakeLLM":
        self.script = other.script
        self.bound = other.bound
        self.methods = other.methods
        return self

    def with_structured_output(self, schema: type[BaseModel], method: str = "") -> "FakeLLM":
        self.methods.append(method)
        return self

    def invoke(self, messages: Any, config: Any = None) -> Any:
        self.bound.append(self.max_tokens)
        nxt = self.script.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt


@pytest.fixture
def config() -> AgentConfig:
    cfg = AgentConfig()
    cfg.max_tokens = 4096
    cfg.context_window = 16_384
    return cfg


def test_a_finished_object_comes_back_as_a_value(config) -> None:
    llm = FakeLLM([Answer(text="ok")])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert outcome.ok
    assert outcome.value.text == "ok"
    assert outcome.reason is None


def test_running_out_of_tokens_retries_with_headroom(config) -> None:
    llm = FakeLLM([_length_error(), Answer(text="finished")])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert outcome.ok
    assert outcome.value.text == "finished"
    assert llm.bound == [4096, 8192]
    assert llm.methods == ["json_schema", "json_schema"]


def test_the_retry_is_skipped_when_the_window_cannot_hold_it(config) -> None:
    llm = FakeLLM([_length_error(), _length_error()])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "u" * 22_000)

    assert not outcome.ok
    assert outcome.reason == "length"
    assert llm.bound == [4096, 4096]


def test_an_endpoint_that_rejects_reasoning_effort_is_asked_once(config) -> None:
    config.reasoning_effort = "low"
    llm = FakeLLM([Answer(text="ok")])
    caller = StructuredCaller(config, llm=llm)
    assert caller._effort_supported

    rebuilt: list[str] = []
    caller.llm = llm

    def _rebuild(cfg, *, reasoning_effort=None):
        rebuilt.append(reasoning_effort)
        return llm

    import agent.llm as llm_module

    original = llm_module.make_llm
    llm_module.make_llm = _rebuild
    try:
        dropped = caller._drop_effort_if_rejected(
            RuntimeError("Error code: 400 - unrecognised parameter reasoning_effort")
        )
    finally:
        llm_module.make_llm = original

    assert dropped
    assert rebuilt == [""]
    assert not caller._effort_supported
    assert not caller._drop_effort_if_rejected(RuntimeError("reasoning_effort again"))
    fresh = StructuredCaller(config, llm=llm)
    assert not fresh._drop_effort_if_rejected(RuntimeError("timeout contacting deepseek-reasoner"))
    assert fresh._effort_supported


def test_a_template_that_refuses_the_effort_value_is_recognised(config) -> None:
    config.reasoning_effort = "high"
    llm = FakeLLM([Answer(text="ok")])
    caller = StructuredCaller(config, llm=llm)

    import agent.llm as llm_module

    original = llm_module.make_llm
    llm_module.make_llm = lambda cfg, *, reasoning_effort=None: llm
    try:
        dropped = caller._drop_effort_if_rejected(
            RuntimeError("Unexpected reasoning effort high. Supported types are xhigh (default), medium, and low.")
        )
    finally:
        llm_module.make_llm = original

    assert dropped
    assert not caller._effort_supported


def test_a_model_too_small_gives_up_and_says_why(config) -> None:
    llm = FakeLLM([_length_error(), _length_error(), _length_error(), _length_error()])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert not outcome.ok
    assert outcome.value is None
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
    assert Outcome.of(Answer(text="x")).ok
    assert not Outcome.failed("length").ok
    assert Outcome.failed("length").value is None


def test_the_headroom_is_measured_from_the_reply_not_guessed_from_the_prompt(config) -> None:
    llm = FakeLLM([_length_error(prompt_tokens=6_152), Answer(text="finished")])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "u" * 32_000)

    assert outcome.ok
    assert llm.bound == [4096, 8192], "the measured prompt left ample room"


def test_a_measured_prompt_that_really_does_fill_the_window_skips_the_retry(config) -> None:
    llm = FakeLLM([_length_error(prompt_tokens=15_000), _length_error(prompt_tokens=15_000)])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert not outcome.ok
    assert outcome.reason == "length"
    assert llm.bound == [4096, 4096], "no room to double, so no second identical request"


def test_the_headroom_is_clamped_to_what_is_left_not_simply_doubled(config) -> None:
    llm = FakeLLM([_length_error(prompt_tokens=9_000), Answer(text="finished")])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert outcome.ok
    assert llm.bound == [4096, 5884]
