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
#: tokens mid-object; `refused` is a well-formed reply of the wrong type;
#: `transport` is everything else -- a timeout, a dead endpoint, a parser the
#: server does not have.
FailureReason = Literal["length", "refused", "transport"]


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


def make_llm(config: AgentConfig) -> ChatOpenAI:
    """``require_model`` here so a missing model fails at construction, not at
    the first request part-way through a long run."""
    return ChatOpenAI(
        base_url=config.base_url,
        api_key=config.api_key,  # type: ignore[arg-type]
        model=config.require_model(),
        temperature=config.temperature,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
        # Aliased: the field is `max_tokens`, the constructor takes the alias.
        max_completion_tokens=config.max_tokens,
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

    def _runnable(self, schema: type[ModelT], method: StructuredMethod, headroom: int | None = None) -> Any:
        llm = self.llm if headroom is None else self.llm.bind(max_completion_tokens=headroom)
        return llm.with_structured_output(schema, method=method)

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
            except LengthFinishReasonError:
                # Guided decoding guarantees shape, not termination: a model too
                # small for the schema emits a valid prefix until it runs out.
                #
                # Retried with double the headroom on the *same* method, not
                # fallen through to the next one. Running out of tokens is not a
                # method problem, so `function_calling` would fail identically --
                # which is what used to happen, burning a second call to learn
                # nothing. One more try at twice the ceiling either finishes the
                # object or establishes that the model is the wrong size.
                headroom = self.config.max_tokens * 2
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
