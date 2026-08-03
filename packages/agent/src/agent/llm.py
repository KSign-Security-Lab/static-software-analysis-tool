"""The single place a model gets called.

vLLM runs as a separate OpenAI-compatible server, so this package needs the
client and not ``vllm`` itself. Two structured-output paths exist and both are
handled here rather than at call sites:

``response_format={"type": "json_schema", ...}``
    The OpenAI-standard form, and what ``with_structured_output(method=
    "json_schema")`` emits. Confirmed working against a served model.

``extra_body={"structured_outputs": {"json": schema}}``
    vLLM's own form. Kept as a fallback because guided decoding support varies
    between vLLM builds and backends (``xgrammar``, ``guidance``).

Keeping both behind one function means switching is a configuration change, not
a refactor.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Literal, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from openai import LengthFinishReasonError
from pydantic import BaseModel

from .config import AgentConfig

log = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=BaseModel)

StructuredMethod = Literal["json_schema", "function_calling"]

#: Tried in order. ``json_schema`` is real constrained decoding; the tool-calling
#: path is a fallback for endpoints that expose function calling but not guided
#: JSON.
STRUCTURED_METHODS: tuple[StructuredMethod, ...] = ("json_schema", "function_calling")


def make_llm(config: AgentConfig) -> ChatOpenAI:
    """A client for the configured endpoint.

    ``require_model`` is called here so a missing model fails at construction
    with an actionable message, rather than at the first request part-way
    through a long run.
    """
    return ChatOpenAI(
        base_url=config.base_url,
        api_key=config.api_key,  # type: ignore[arg-type]
        model=config.require_model(),
        temperature=config.temperature,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
        # The field is `max_tokens`, but it is aliased and the constructor only
        # accepts the alias.
        max_completion_tokens=config.max_tokens,
    )


class StructuredCaller:
    """Calls the model and returns a validated pydantic object, or None.

    None rather than an exception: one chunk whose output will not parse must
    not abort an inspection that is forty minutes in. The failure is counted and
    reported instead.
    """

    def __init__(self, config: AgentConfig, llm: ChatOpenAI | None = None) -> None:
        self.config = config
        self.llm = llm if llm is not None else make_llm(config)
        #: Which method worked, remembered after the first success so later
        #: calls do not re-pay for probing a path the endpoint rejects.
        self._method: StructuredMethod | None = None
        #: Cleared permanently the first time the endpoint refuses tool calling,
        #: so one unsupported server does not produce one warning per finding.
        self.tools_available = config.enable_tools

    def _runnable(self, schema: type[ModelT], method: StructuredMethod) -> Any:
        return self.llm.with_structured_output(schema, method=method)

    def call(self, schema: type[ModelT], system: str, user: str) -> ModelT | None:
        """One structured call. Returns None if nothing usable came back."""
        messages = [("system", system), ("human", user)]
        methods: tuple[StructuredMethod, ...] = (self._method,) if self._method else STRUCTURED_METHODS

        for method in methods:
            try:
                result = self._runnable(schema, method).invoke(messages)
            except LengthFinishReasonError:
                # Guided decoding guarantees the shape, not termination: a model
                # too small for the schema emits a valid prefix until it runs
                # out of room. Worth naming, because it looks like a protocol
                # failure and is not one.
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
                    # vLLM rejects tool calling unless the server was started
                    # with a parser for the model family, so this fallback is
                    # unavailable rather than broken.
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

    def gather(self, system: str, user: str, session: Any, budget: int) -> str:
        """Let the model call tools, and return a transcript of what came back.

        Bounded and single-purpose: this collects material for a verdict, it
        does not produce one. The verdict is a separate guided-decoding call, so
        tool calling never has to also be responsible for schema conformance.

        Returns "" when tools are unusable, which is a normal outcome -- vLLM
        rejects tool calling unless the server was started with
        ``--tool-call-parser`` for the model family. That degrades verification
        to context-only rather than failing the run, and is reported once.
        """
        if not self.tools_available or budget <= 0:
            return ""

        tools = session.tools
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
                reply = bound.invoke(messages)
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
        """Turn tools off for the rest of the run, once, with a reason."""
        if self.tools_available:
            self.tools_available = False
            log.warning(
                "tool calling is unavailable on this endpoint, verifying from context only. "
                "vLLM needs --tool-call-parser for the model family. (%s)",
                str(err)[:200],
            )
