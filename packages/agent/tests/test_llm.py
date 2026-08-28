"""What a structured call does when the model does not finish.

The bug these cover: `call` used to return `None` for both "the model
considered this and found nothing" and "the call died", so callers could not
tell them apart -- and two of them chose to read a dead call as a negative
answer. A run of three files lost the memory analysis of two units and the
patch for a reported finding that way, and reported itself complete.
"""

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
    """The real exception, constructed the way the client raises it.

    With ``prompt_tokens`` it also carries the usage the client attaches, which
    is what the retry reads to size its headroom. Without, it stands for the
    streaming case where the client cannot attach one.
    """
    err = LengthFinishReasonError.__new__(LengthFinishReasonError)
    if prompt_tokens is not None:
        err.completion = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=prompt_tokens))
    return err


class FakeLLM:
    """Answers from a script, and records the ceiling each call actually carried.

    Modelled on langchain's real behaviour rather than on the convenient one,
    which is the point. The previous stub had a ``bind`` that returned a clone
    whose ``with_structured_output`` kept the bound ceiling -- so the retry test
    passed against code that sent 4096 twice. The real ``RunnableBinding``
    proxies attribute access to the *unbound* model and drops its kwargs, so
    ``bind(...).with_structured_output(...)`` loses the ceiling entirely.

    ``bind`` here reproduces that: it returns something whose
    ``with_structured_output`` has forgotten the binding, exactly as the library
    does. ``model_copy`` is the path that works, and is what the caller uses.
    """

    def __init__(self, script: list[Any], max_tokens: int = 4096) -> None:
        self.script = script
        self.max_tokens = max_tokens
        #: The ceiling in force for each `invoke`, in order.
        self.bound: list[int | None] = []
        self.methods: list[str] = []

    def bind(self, **kwargs: Any) -> "FakeLLM":
        # Deliberately drops the kwargs on the next `with_structured_output`,
        # the way RunnableBinding.__getattr__ does.
        return FakeLLM(self.script, self.max_tokens)._share(self)

    def model_copy(self, update: dict[str, Any] | None = None) -> "FakeLLM":
        clone = FakeLLM(self.script, (update or {}).get("max_tokens", self.max_tokens))
        return clone._share(self)

    def _share(self, other: "FakeLLM") -> "FakeLLM":
        """One script and one set of records across every copy."""
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
    # Stated, so `_headroom` does no network probe and the arithmetic below is
    # the endpoint this project actually runs against.
    cfg.context_window = 16_384
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
    # Twice, and the second genuinely at double the ceiling -- not merely asked
    # for. This is the assertion the old stub could not make: `bind` drops the
    # ceiling on the way to `with_structured_output`, so a run whose retry
    # "worked" was re-sending 4096 and failing identically 264 times.
    assert llm.bound == [4096, 8192]
    # Same method both times; the fallback was never reached.
    assert llm.methods == ["json_schema", "json_schema"]


def test_the_retry_is_skipped_when_the_window_cannot_hold_it(config) -> None:
    """Doubling a ceiling the window has no room for is a 400, not a retry.

    In run dbd2c9e7ca62, 89 of 749 truncations had a prompt that left less than
    the doubled ceiling. Asking anyway would turn a length failure into a
    transport one and lose the reason.
    """
    llm = FakeLLM([_length_error(), _length_error()])
    # 16384 window, 1.6 chars per token: a prompt this long leaves under 4096.
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "u" * 22_000)

    assert not outcome.ok
    assert outcome.reason == "length"
    # One attempt per method, and no doubled retry under either.
    assert llm.bound == [4096, 4096]


def test_an_endpoint_that_rejects_reasoning_effort_is_asked_once(config) -> None:
    """A ceiling on reasoning is worth a lot where it exists and is a 400 where
    it does not. Dropped for the run rather than per call."""
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
    # Asked once: a second objection is not worth another rebuild.
    assert not caller._drop_effort_if_rejected(RuntimeError("reasoning_effort again"))
    # And the word alone is not an objection: a model named for its reasoning
    # appearing in a timeout must not cost every later completion its ceiling.
    fresh = StructuredCaller(config, llm=llm)
    assert not fresh._drop_effort_if_rejected(RuntimeError("timeout contacting deepseek-reasoner"))
    assert fresh._effort_supported


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


def test_the_headroom_is_measured_from_the_reply_not_guessed_from_the_prompt(config) -> None:
    """The exception carries the usage that produced it, so guessing is a choice.

    It is not a close guess. On the first run with the repaired retry, counting
    characters put three prompts at ~20 000 tokens that the endpoint had just
    counted at ~6 000 -- so two calls with 8 700 tokens of room going spare were
    told there was none and never retried. `chars_per_token` is a lower bound on
    density by design, which makes it an over-estimate of a prompt: the safe
    direction when deciding what to send, the wrong one when deciding what is
    left.
    """
    llm = FakeLLM([_length_error(prompt_tokens=6_152), Answer(text="finished")])
    # Long enough that the character estimate would compute negative room and
    # skip the retry -- which is exactly what it did in production.
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
    """Between the two: room for more than it had, less than twice as much."""
    # 16384 - 9000 - 1500 = 5884, which is above 4096 and below 8192.
    llm = FakeLLM([_length_error(prompt_tokens=9_000), Answer(text="finished")])
    outcome = StructuredCaller(config, llm=llm).call(Answer, "sys", "usr")

    assert outcome.ok
    assert llm.bound == [4096, 5884]
