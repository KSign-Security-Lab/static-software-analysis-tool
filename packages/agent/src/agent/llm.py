"""The single place a model gets called.

vLLM is a separate server, so this needs the OpenAI client, not ``vllm``.
Structured output goes through ``json_schema`` guided decoding, falling back to
tool calling; keeping both here makes switching a config change.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, Sequence, TypeVar

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
    """Returns a validated pydantic object, or None.

    None rather than raising: one unparseable chunk must not abort a run that is
    forty minutes in. The failure is counted instead.
    """

    def __init__(self, config: AgentConfig, llm: ChatOpenAI | None = None) -> None:
        self.config = config
        self.llm = llm if llm is not None else make_llm(config)
        # Remembered after first success so later calls skip the probe.
        self._method: StructuredMethod | None = None
        # Cleared for the run on first refusal, so one unsupported server does
        # not warn once per finding.
        self.tools_available = config.enable_tools

    def _runnable(self, schema: type[ModelT], method: StructuredMethod) -> Any:
        return self.llm.with_structured_output(schema, method=method)

    def call(
        self,
        schema: type[ModelT],
        system: str,
        user: str,
        trace: RunnableConfig | None = None,
    ) -> ModelT | None:
        """One structured call. ``trace`` is inert when tracing is off."""
        messages = [("system", system), ("human", user)]
        methods: tuple[StructuredMethod, ...] = (self._method,) if self._method else STRUCTURED_METHODS

        for method in methods:
            try:
                result = self._runnable(schema, method).invoke(messages, config=trace)
            except LengthFinishReasonError:
                # Guided decoding guarantees shape, not termination. Named
                # because it looks like a protocol failure and is not one.
                log.warning(
                    "%s did not finish a %s object within max_tokens -- the model is probably "
                    "too small for this schema. Try a larger one, or raise AGENT_MAX_TOKENS.",
                    method,
                    schema.__name__,
                )
                continue
            except Exception as err:  # noqa: BLE001 - any client/model failure is the same to us
                log.warning("structured call failed via %s: %s", method, err)
                if "tool-call-parser" in str(err):
                    # Unavailable rather than broken: vLLM needs a parser flag.
                    log.warning(
                        "the endpoint needs --tool-call-parser for the function_calling fallback; "
                        "json_schema is the supported path"
                    )
                continue
            if isinstance(result, schema):
                self._method = method
                return result
            log.warning("structured call via %s returned %s, not %s", method, type(result), schema.__name__)

        # A remembered method that has started failing should not stay pinned.
        if self._method is not None:
            self._method = None
        return None

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
