from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass
from typing import Any, Callable, Generic, Literal, Sequence, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from openai import LengthFinishReasonError
from pydantic import BaseModel

from .config import AgentConfig

log = logging.getLogger(__name__)
ModelT = TypeVar("ModelT", bound=BaseModel)
StructuredMethod = Literal["json_schema", "function_calling"]
STRUCTURED_METHODS: tuple[StructuredMethod, ...] = ("json_schema", "function_calling")
FailureReason = Literal["length", "too_long", "refused", "transport", "cancelled"]


class Cancelled(Exception):
    pass


def _is_overflow(err: Exception) -> bool:
    text = str(err).lower()
    if "max_tokens must be at least 1" in text:
        return True
    return "context length" in text or "maximum context" in text or "longer than the maximum" in text


@dataclass(frozen=True)
class Outcome(Generic[ModelT]):
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
    effort = config.reasoning_effort if reasoning_effort is None else reasoning_effort
    return ChatOpenAI(
        base_url=config.base_url,
        api_key=config.api_key,  # type: ignore[arg-type]
        model=config.require_model(),
        temperature=config.temperature,
        timeout=config.request_timeout,
        max_retries=config.max_retries,
        max_completion_tokens=config.max_tokens,
        reasoning_effort=effort or None,
    )


class StructuredCaller:
    def __init__(self, config: AgentConfig, llm: ChatOpenAI | None = None) -> None:
        self.config = config
        self._lock = threading.Lock()
        # The only bound on what reaches the endpoint. The graph may have far more
        # tasks runnable than the server has room for -- a nested subgraph brings its
        # own thread pool -- so the ceiling cannot live in the graph's shape.
        self._slots = threading.BoundedSemaphore(max(1, config.max_inflight))
        self.cancelled: Callable[[], bool] = lambda: False
        self.llm = llm if llm is not None else make_llm(config)
        self._method: StructuredMethod | None = None
        self.tools_available = config.enable_tools
        self._effort_supported = bool(config.reasoning_effort)

    def _runnable(self, schema: type[ModelT], method: StructuredMethod, headroom: int | None = None) -> Any:
        with self._lock:
            current = self.llm
        llm = current if headroom is None else current.model_copy(update={"max_tokens": headroom})
        return llm.with_structured_output(schema, method=method)

    def _invoke(self, runnable: Any, messages: Any, trace: RunnableConfig | None) -> Any:
        if self.cancelled():
            raise Cancelled()
        with self._slots:
            # Checked again on the way in: a run cancelled while this was queued must
            # not spend a slot, or cancelling costs one full call per queued task.
            if self.cancelled():
                raise Cancelled()
            return runnable.invoke(messages, config=trace)

    # vLLM frees a sequence when its client goes away, so closing the transport is
    # what ends requests already on the wire. Without it a killed run leaves the
    # server decoding into nothing.
    def abort(self) -> None:
        try:
            self.llm.root_client.close()
        except Exception:  # noqa: BLE001 - an abort must not raise
            log.debug("could not close the endpoint transport", exc_info=True)

    def _headroom(self, err: LengthFinishReasonError, prompt: str, system: str) -> int | None:
        window = self.config.resolve_window()
        doubled = self.config.max_tokens * 2
        if not window:
            return doubled

        usage = getattr(getattr(err, "completion", None), "usage", None)
        used = getattr(usage, "prompt_tokens", None)
        if not used:
            used = int((len(prompt) + len(system)) / max(self.config.chars_per_token, 0.1))

        headroom = min(doubled, window - used - self.config.OVERHEAD_TOKENS)
        return headroom if headroom > self.config.max_tokens else None

    def _drop_effort_if_rejected(self, err: Exception) -> bool:
        with self._lock:
            if not self._effort_supported:
                return False
        text = str(err)
        if "reasoning_effort" not in text and "reasoning effort" not in text:
            return False
        with self._lock:
            if not self._effort_supported:
                return True
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
        messages = [("system", system), ("human", user)]
        with self._lock:
            pinned = self._method
        methods: tuple[StructuredMethod, ...] = (pinned,) if pinned else STRUCTURED_METHODS
        last: FailureReason = "transport"

        for method in methods:
            try:
                result = self._invoke(self._runnable(schema, method), messages, trace)
            except Cancelled:
                return Outcome.failed("cancelled")
            except LengthFinishReasonError as length_err:
                headroom = self._headroom(length_err, user, system)
                if headroom is None:
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
                    result = self._invoke(self._runnable(schema, method, headroom=headroom), messages, trace)
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
                    log.warning("prompt does not fit the window for %s: %s", schema.__name__, err)
                    return Outcome.failed("too_long")
                if self._drop_effort_if_rejected(err):
                    try:
                        result = self._invoke(self._runnable(schema, method), messages, trace)
                    except Exception as retried:  # noqa: BLE001
                        log.warning("structured call failed via %s after dropping effort: %s", method, retried)
                        last = "transport"
                        continue
                    if isinstance(result, schema):
                        self._remember(method)
                        return Outcome.of(result)
                    last = "refused"
                    continue
                log.warning("structured call failed via %s: %s", method, err)
                if "tool-call-parser" in str(err):
                    log.warning(
                        "the endpoint needs --tool-call-parser for the function_calling fallback; "
                        "json_schema is the supported path"
                    )
                last = "transport"
                continue
            if isinstance(result, schema):
                self._remember(method)
                return Outcome.of(result)
            log.warning("structured call via %s returned %s, not %s", method, type(result), schema.__name__)
            last = "refused"

        with self._lock:
            self._method = None
        return Outcome.failed(last)

    def _remember(self, method: StructuredMethod) -> None:
        with self._lock:
            self._method = method

    def gather(
        self,
        system: str,
        user: str,
        session: Any,
        budget: int,
        trace: RunnableConfig | None = None,
        allowed: Sequence[str] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> str:
        if not self.tools_available or budget <= 0:
            return ""

        tools = session.tools
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
            if cancelled is not None and cancelled():
                break
            try:
                reply = self._invoke(bound, messages, trace)
            except Cancelled:
                break
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
        with self._lock:
            if not self.tools_available:
                return
            self.tools_available = False
        log.warning(
            "tool calling is unavailable on this endpoint, verifying from context only. "
            "vLLM needs --tool-call-parser for the model family. (%s)",
            str(err)[:200],
        )
