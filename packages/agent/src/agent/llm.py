"""The single place a model gets called.

vLLM is a separate server, so this needs the OpenAI client, not ``vllm``.
Structured output goes through ``json_schema`` guided decoding, falling back to
tool calling; keeping both here makes switching a config change.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Generic, Literal, Sequence, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from openai import LengthFinishReasonError
from pydantic import BaseModel

from .config import AgentConfig

log = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

StructuredMethod = Literal["json_schema", "function_calling"]

# json_schema is real constrained decoding; function_calling is the fallback.
STRUCTURED_METHODS: tuple[StructuredMethod, ...] = ("json_schema", "function_calling")

#: Why a call produced nothing. `length` is the model running out of completion
#: tokens mid-object; `too_long` is the *prompt* not fitting the window, which is
#: the opposite problem and has the opposite fix; `refused` is a well-formed
#: reply of the wrong type; `transport` is everything else -- a timeout, a dead
#: endpoint, a parser the server does not have.
#:
#: `too_long` is split out because it was reaching a reader as `transport`, so a
#: prompt three times the size of the window was indistinguishable on screen
#: from a model that was switched off.
FailureReason = Literal["length", "too_long", "refused", "transport"]


def _is_overflow(err: Exception) -> bool:
    """Whether this failure is the prompt being bigger than the window.

    vLLM says it two ways depending on whether a ceiling was sent: with one, the
    request is longer than the model can take; without, it derives a negative
    default and complains that `max_tokens must be at least 1, got -43420`.
    """
    text = str(err).lower()
    if "max_tokens must be at least 1" in text:
        return True
    return "context length" in text or "maximum context" in text or "longer than the maximum" in text


@dataclass(frozen=True)
class Outcome(Generic[ModelT]):
    """What a structured call produced, or why it produced nothing.

    This exists because `None` used to mean both. A caller could not tell "the
    model considered this and found nothing" from "the call died", so each of
    the five call sites invented its own policy -- and two of them chose to
    treat a dead call as a negative answer. `verify` recorded a transport
    failure as a considered refutation, which is not a missing answer but a
    wrong one.

    A run of three files lost the memory analysis of two units and the patch for
    a reported finding this way, and reported itself complete.
    """

    value: ModelT | None = None
    reason: FailureReason | None = None

    @property
    def ok(self) -> bool:
        return self.value is not None

    @classmethod
    def of(cls, value: ModelT) -> "Outcome[ModelT]":
        return cls(value=value)

    @classmethod
    def failed(cls, reason: FailureReason) -> "Outcome[ModelT]":
        return cls(reason=reason)


def make_llm(config: AgentConfig, *, reasoning_effort: str | None = None) -> ChatOpenAI:
    """``require_model`` here so a missing model fails at construction, not at
    the first request part-way through a long run.

    ``reasoning_effort`` overrides the config's, so a caller that has learned the
    endpoint rejects it can rebuild without one.
    """
    effort = config.reasoning_effort if reasoning_effort is None else reasoning_effort
    return ChatOpenAI(
        base_url=config.base_url,
        api_key=config.api_key,  # type: ignore[arg-type]
        model=config.require_model(),
        temperature=config.temperature,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
        # Aliased: the field is `max_tokens`, the constructor takes the alias.
        max_completion_tokens=config.max_tokens,
        # None is excluded from the payload; a server that has never heard of the
        # parameter should not be sent one.
        reasoning_effort=effort or None,
    )


class StructuredCaller:
    """Returns a validated pydantic object, or why there is not one.

    An `Outcome` rather than raising: one unparseable chunk must not abort a run
    that is forty minutes in. And an `Outcome` rather than `None`, because the
    docstring here used to promise the failure was counted instead and nothing
    ever counted it -- so a dead call and a negative answer were the same value,
    and two call sites quietly chose to read it as the second.
    """

    def __init__(self, config: AgentConfig, llm: ChatOpenAI | None = None) -> None:
        self.config = config
        self.llm = llm if llm is not None else make_llm(config)
        # Remembered after first success so later calls skip the probe.
        self._method: StructuredMethod | None = None
        # Cleared for the run on first refusal, so one unsupported server does
        # not warn once per finding.
        self.tools_available = config.enable_tools
        # Same shape, same reason. A reasoning ceiling is worth a lot on a model
        # that has one and is a 400 on a model that does not, so it is dropped
        # for the run the first time a server objects rather than per call.
        self._effort_supported = bool(config.reasoning_effort)

    def _runnable(self, schema: type[ModelT], method: StructuredMethod, headroom: int | None = None) -> Any:
        """The chain for one call, optionally at a raised completion ceiling.

        ``model_copy`` rather than ``bind``, and that is the whole of a bug that
        made the retry below a no-op for every run this project has done.
        ``bind`` returns a ``RunnableBinding``, whose ``__getattr__`` fetches the
        attribute off ``self.bound`` and drops ``self.kwargs`` -- so
        ``with_structured_output`` was called on the *unbound* model and the
        headroom went nowhere. The retry re-sent the identical request and
        failed identically: in run dbd2c9e7ca62, 264 calls did this, each pair
        of spans capped at exactly 4096 completion tokens.

        Copying the model puts the ceiling in ``_default_params``, where
        ``with_structured_output`` cannot lose it.
        """
        llm = self.llm if headroom is None else self.llm.model_copy(update={"max_tokens": headroom})
        return llm.with_structured_output(schema, method=method)

    def _headroom(self, err: LengthFinishReasonError, prompt: str, system: str) -> int | None:
        """A raised ceiling that still fits the window, or None if none does.

        Doubling the ceiling is only useful if the window can hold it. It often
        could not: in 89 of the 749 truncations in run dbd2c9e7ca62 the prompt
        plus a doubled ceiling was past the endpoint's 16 384, so raising it
        blindly turns a length failure into a 400.

        The prompt is *measured*, not estimated. The exception carries the usage
        that produced it, so the exact figure is in hand -- and the estimate is
        not close enough to substitute: on the first run with this retry working,
        counting characters put three prompts at ~20 000 tokens that the endpoint
        had just counted at ~6 000, and the retry was skipped for two calls with
        8 700 tokens of room going spare. `chars_per_token` is deliberately a
        lower bound on density, which makes it an *over*-estimate of a prompt --
        the safe direction when budgeting what to send, and the wrong one here.

        Returns None when there is no more room than the call already had, which
        is the honest answer: a second identical request is what the retry did
        before it was repaired, and it costs a minute to learn nothing.
        """
        window = self.config.resolve_window()
        doubled = self.config.max_tokens * 2
        if not window:
            # An endpoint that will not say leaves us where we were.
            return doubled

        usage = getattr(getattr(err, "completion", None), "usage", None)
        used = getattr(usage, "prompt_tokens", None)
        if not used:
            # Streaming omits usage. Fall back to the estimate, conservative on
            # purpose: guessing the prompt is small is how this becomes a 400.
            used = int((len(prompt) + len(system)) / max(self.config.chars_per_token, 0.1))

        headroom = min(doubled, window - used - self.config.OVERHEAD_TOKENS)
        return headroom if headroom > self.config.max_tokens else None

    def _drop_effort_if_rejected(self, err: Exception) -> bool:
        """Give up the reasoning ceiling if this endpoint will not take one.

        True when the model was rebuilt without it and the call is worth trying
        again. An endpoint either supports the parameter or does not, so this
        fires at most once per run.
        """
        if not self._effort_supported:
            return False
        # The parameter's own name, not merely the word: a model called
        # `deepseek-reasoner` in an unrelated timeout message is not an endpoint
        # objecting to a parameter, and dropping the setting on that would make
        # every completion afterwards longer for no reason.
        if "reasoning_effort" not in str(err):
            return False
        log.warning(
            "%s does not accept reasoning_effort; continuing without it. Completions on a "
            "reasoning model may run out of tokens mid-object as a result.",
            self.config.base_url,
        )
        self._effort_supported = False
        self.llm = make_llm(self.config, reasoning_effort="")
        self._method = None
        return True

    def call(
        self,
        schema: type[ModelT],
        system: str,
        user: str,
        trace: RunnableConfig | None = None,
    ) -> Outcome[ModelT]:
        """One structured call, as a value or a reason. ``trace`` is inert when tracing is off."""
        messages = [("system", system), ("human", user)]
        methods: tuple[StructuredMethod, ...] = (self._method,) if self._method else STRUCTURED_METHODS
        last: FailureReason = "transport"

        for method in methods:
            try:
                result = self._runnable(schema, method).invoke(messages, config=trace)
            except LengthFinishReasonError as length_err:
                # Guided decoding guarantees shape, not termination: a model too
                # small for the schema emits a valid prefix until it runs out.
                #
                # Retried with double the headroom on the *same* method, not
                # fallen through to the next one. Running out of tokens is not a
                # method problem, so `function_calling` would fail identically --
                # which is what used to happen, burning a second call to learn
                # nothing. One more try at twice the ceiling either finishes the
                # object or establishes that the model is the wrong size.
                headroom = self._headroom(length_err, user, system)
                if headroom is None:
                    # The window has no more to give, so a retry would be the
                    # same request again. Said once, and counted as a length
                    # failure -- which is what it is.
                    log.warning(
                        "%s did not finish a %s object within %d tokens, and the window has no "
                        "room to raise it -- shorten the prompt or use a model with a larger one.",
                        method,
                        schema.__name__,
                        self.config.max_tokens,
                    )
                    last = "length"
                    continue
                log.warning(
                    "%s did not finish a %s object within %d tokens; retrying at %d",
                    method,
                    schema.__name__,
                    self.config.max_tokens,
                    headroom,
                )
                try:
                    result = self._runnable(schema, method, headroom=headroom).invoke(messages, config=trace)
                except LengthFinishReasonError:
                    log.warning(
                        "%s still did not finish a %s object within %d tokens -- the model is "
                        "probably too small for this schema. Try a larger one, or raise "
                        "AGENT_MAX_TOKENS.",
                        method,
                        schema.__name__,
                        headroom,
                    )
                    last = "length"
                    continue
                except Exception as err:  # noqa: BLE001
                    log.warning("retry after length failure failed via %s: %s", method, err)
                    last = "transport"
                    continue
            except Exception as err:  # noqa: BLE001 - any client/model failure is the same to us
                if _is_overflow(err):
                    # Not a method problem and not worth a second method: the
                    # prompt is too big and would be equally too big next time.
                    log.warning("prompt does not fit the window for %s: %s", schema.__name__, err)
                    return Outcome.failed("too_long")
                if self._drop_effort_if_rejected(err):
                    # Rebuilt without the parameter; this attempt still counts as
                    # one, so retry the same method once rather than falling
                    # through and blaming the method.
                    try:
                        result = self._runnable(schema, method).invoke(messages, config=trace)
                    except Exception as retried:  # noqa: BLE001
                        log.warning("structured call failed via %s after dropping effort: %s", method, retried)
                        last = "transport"
                        continue
                    if isinstance(result, schema):
                        self._method = method
                        return Outcome.of(result)
                    last = "refused"
                    continue
                log.warning("structured call failed via %s: %s", method, err)
                if "tool-call-parser" in str(err):
                    # Unavailable rather than broken: vLLM needs a parser flag.
                    log.warning(
                        "the endpoint needs --tool-call-parser for the function_calling fallback; "
                        "json_schema is the supported path"
                    )
                last = "transport"
                continue
            if isinstance(result, schema):
                self._method = method
                return Outcome.of(result)
            log.warning("structured call via %s returned %s, not %s", method, type(result), schema.__name__)
            last = "refused"

        # A remembered method that has started failing should not stay pinned.
        if self._method is not None:
            self._method = None
        return Outcome.failed(last)

    def gather(
        self,
        system: str,
        user: str,
        session: Any,
        budget: int,
        trace: RunnableConfig | None = None,
        allowed: Sequence[str] | None = None,
    ) -> str:
        """Let the model call tools; return a transcript.

        Collects material for a verdict, never produces one -- the verdict is a
        separate guided-decoding call, so tool calling is not also responsible
        for schema conformance. Returns "" when tools are unusable, which
        degrades verification to context-only rather than failing the run.
        """
        if not self.tools_available or budget <= 0:
            return ""

        tools = session.tools
        # The session allows every tool any step may use, because it is opened
        # once per run. Which of them *this* step may see is decided here, so a
        # specialist offered four lookups is not also offered a sandbox.
        if allowed is not None:
            names = set(allowed)
            tools = [tool for tool in tools if tool.name in names]
        if not tools:
            return ""

        try:
            bound = self.llm.bind_tools(tools)
        except Exception as err:  # noqa: BLE001
            self._disable_tools(err)
            return ""

        messages: list[Any] = [SystemMessage(content=system), HumanMessage(content=user)]
        transcript: list[str] = []

        for _ in range(budget):
            try:
                reply = bound.invoke(messages, config=trace)
            except Exception as err:  # noqa: BLE001
                if "tool-call-parser" in str(err) or "tool_choice" in str(err):
                    self._disable_tools(err)
                else:
                    log.warning("tool-gathering call failed: %s", err)
                break

            calls = getattr(reply, "tool_calls", None) or []
            if not calls:
                break

            messages.append(reply)
            for call in calls:
                name = call.get("name", "")
                args = call.get("args", {}) or {}
                result = session.call(name, args)
                transcript.append(f"$ {name}({json.dumps(args, default=str)[:200]})\n{result[:4000]}")
                messages.append(ToolMessage(content=result[:4000], tool_call_id=call.get("id", name)))

        return "\n\n".join(transcript)

    def _disable_tools(self, err: object) -> None:
        """Off for the rest of the run, once, with a reason."""
        if self.tools_available:
            self.tools_available = False
            log.warning(
                "tool calling is unavailable on this endpoint, verifying from context only. "
                "vLLM needs --tool-call-parser for the model family. (%s)",
                str(err)[:200],
            )
