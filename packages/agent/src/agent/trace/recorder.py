"""A LangChain callback handler that writes spans to the run's own store.

Attached through the ``config`` already built for each call, so it sees the
whole tree -- graph nodes, the LLM calls under them, the tool calls under those
-- rather than only what the call sites happen to report.

Never raises. A tracer that can break an inspection is worse than no tracer, so
every hook swallows its own failures.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Sequence
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from .store import SpanStore

log = logging.getLogger(__name__)


def _tokens(response: Any) -> int | None:
    usage = getattr(response, "llm_output", None) or {}
    if isinstance(usage, dict):
        counts = usage.get("token_usage") or usage.get("usage") or {}
        if isinstance(counts, dict):
            total = counts.get("total_tokens")
            if isinstance(total, int):
                return total
    return None


def _messages(batches: Sequence[Sequence[Any]]) -> list[dict[str, str]]:
    """Chat messages, flattened to something readable in the UI."""
    out: list[dict[str, str]] = []
    for batch in batches:
        for message in batch:
            out.append(
                {
                    "role": getattr(message, "type", message.__class__.__name__),
                    "content": str(getattr(message, "content", message)),
                }
            )
    return out


def _is_step(given: str | None, parent: UUID | None, metadata: dict[str, Any] | None) -> bool:
    """Whether a chain is a step of the agent or framework scaffolding.

    Everything inside a node inherits that node's metadata, so `langgraph_node`
    alone does not separate them -- but the node span is the one *named* after
    its node. The rest are the wrapper `with_structured_output` puts around the
    model, the parser it appends, the routing predicate and the channel writes.
    They were two thirds of the tree and none of them is a step anyone reads.
    """
    if parent is None:
        return True  # the graph itself
    node = (metadata or {}).get("langgraph_node")
    return bool(node) and given == node


class SpanRecorder(BaseCallbackHandler):
    """Persist the call tree of one inspection."""

    def __init__(self, store: SpanStore) -> None:
        self.store = store
        # A tool runs after the model that asked for it has already closed, and
        # LangChain reports it under the graph node instead. Filing it under the
        # model call is what makes a verify step readable as one exchange.
        self._last_llm: str | None = None
        # Dropped spans, and the parent their children should attach to
        # instead, so skipping plumbing does not orphan what ran inside it.
        self._skipped: dict[str, str | None] = {}
        # A skipped wrapper often holds the only meaningful name -- `analyse:fw.c`
        # is set on the sequence, not on the ChatOpenAI inside it.
        self._label: dict[str, str] = {}

    # -- helpers -----------------------------------------------------------

    def _parent_of(self, parent: UUID | None) -> str | None:
        """The nearest ancestor that was actually recorded."""
        current = str(parent) if parent else None
        seen = 0
        while current in self._skipped and seen < 20:
            current = self._skipped[current]
            seen += 1
        return current

    def _inherited(self, parent: UUID | None) -> str | None:
        """A name donated by a skipped ancestor, if it had one."""
        current = str(parent) if parent else None
        seen = 0
        while current is not None and seen < 20:
            if current in self._label:
                return self._label[current]
            if current not in self._skipped:
                return None
            current = self._skipped[current]
            seen += 1
        return None

    def _open(self, run_id: UUID, parent: str | None, name: str, kind: str, inputs: Any, meta: Any) -> None:
        try:
            self.store.start(
                span_id=str(run_id),
                parent_id=parent,
                name=name,
                kind=kind,
                started_at=time.time(),
                inputs=inputs,
                meta=meta if isinstance(meta, dict) else {},
            )
        except Exception as err:  # noqa: BLE001 - tracing must not break the run
            log.debug("span start failed: %s", err)

    def _close(self, run_id: UUID, outputs: Any = None, tokens: int | None = None, error: str | None = None) -> None:
        if str(run_id) in self._skipped:
            return
        try:
            self.store.finish(span_id=str(run_id), ended_at=time.time(), outputs=outputs, tokens=tokens, error=error)
        except Exception as err:  # noqa: BLE001
            log.debug("span finish failed: %s", err)

    # -- chains (graph nodes, runnables) -----------------------------------

    def on_chain_start(
        self,
        serialized: dict[str, Any],
        inputs: dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        given = kwargs.get("name") or (serialized or {}).get("name")
        if not _is_step(given, parent_run_id, metadata):
            self._skipped[str(run_id)] = self._parent_of(parent_run_id)
            # `analyse:fw.c` is set on the wrapper, not on the model inside it,
            # so dropping the wrapper has to hand the name down.
            if given:
                self._label[str(run_id)] = str(given)
            return
        # Graph state is large and mostly the queue; the useful part is which
        # chunk this is, which the metadata already carries.
        self._open(run_id, self._parent_of(parent_run_id), str(given or "chain"), "chain", None, metadata)

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, error=str(error))

    # -- models -------------------------------------------------------------

    def _model_name(self, serialized: dict[str, Any], parent: UUID | None, kwargs: dict[str, Any]) -> str:
        """``analyse:fw.c``, not ``ChatOpenAI``.

        ``with_structured_output`` wraps the model in a sequence, and the
        ``run_name`` lands on the wrapper -- which is plumbing and gets skipped
        -- leaving the model itself with only its class name. Twelve rows all
        called ChatOpenAI is not a trace.
        """
        given = kwargs.get("name")
        if given:
            return str(given)
        return self._inherited(parent) or (serialized or {}).get("name") or "llm"

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._last_llm = str(run_id)
        name = self._model_name(serialized, parent_run_id, kwargs)
        self._open(run_id, self._parent_of(parent_run_id), name, "llm", {"prompts": prompts}, metadata)

    def on_chat_model_start(
        self,
        serialized: dict[str, Any],
        messages: list[list[Any]],
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        self._last_llm = str(run_id)
        name = self._model_name(serialized, parent_run_id, kwargs)
        self._open(run_id, self._parent_of(parent_run_id), name, "llm", {"messages": _messages(messages)}, metadata)

    def on_llm_end(self, response: Any, *, run_id: UUID, **kwargs: Any) -> None:
        text: list[str] = []
        calls: list[Any] = []
        for batch in getattr(response, "generations", []) or []:
            for generation in batch:
                if getattr(generation, "text", ""):
                    text.append(generation.text)
                message = getattr(generation, "message", None)
                # Tool calls live on the message, not as child spans, so they
                # would be invisible in the tree without lifting them here.
                if message is not None and getattr(message, "tool_calls", None):
                    calls.extend(message.tool_calls)
        payload: dict[str, Any] = {}
        if text:
            payload["text"] = text
        if calls:
            payload["tool_calls"] = calls
        self._close(run_id, outputs=payload or None, tokens=_tokens(response))

    def on_llm_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, error=str(error))

    # -- tools ---------------------------------------------------------------

    def on_tool_start(
        self,
        serialized: dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        name = (serialized or {}).get("name") or kwargs.get("name") or "tool"
        # LangChain reports the tool under the graph node, because the gathering
        # loop runs it after the model call that requested it has closed. Filed
        # under that model call instead, so a verify step reads as one exchange:
        # what was asked, what was run, what came back.
        parent = self._last_llm or self._parent_of(parent_run_id)
        self._open(run_id, parent, str(name), "tool", inputs or input_str, metadata)

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, outputs=output)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, error=str(error))
