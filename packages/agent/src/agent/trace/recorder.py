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


class SpanRecorder(BaseCallbackHandler):
    """Persist the call tree of one inspection."""

    def __init__(self, store: SpanStore) -> None:
        self.store = store
        # MCP tools are invoked directly rather than as LangChain runnables, so
        # their callbacks never fire; :meth:`record_tool` files them under the
        # model call that asked for them.
        self._last_llm: str | None = None

    # -- helpers -----------------------------------------------------------

    def _open(self, run_id: UUID, parent: UUID | None, name: str, kind: str, inputs: Any, meta: Any) -> None:
        try:
            self.store.start(
                span_id=str(run_id),
                parent_id=str(parent) if parent else None,
                name=name,
                kind=kind,
                started_at=time.time(),
                inputs=inputs,
                meta=meta if isinstance(meta, dict) else {},
            )
        except Exception as err:  # noqa: BLE001 - tracing must not break the run
            log.debug("span start failed: %s", err)

    def _close(self, run_id: UUID, outputs: Any = None, tokens: int | None = None, error: str | None = None) -> None:
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
        name = kwargs.get("name") or (serialized or {}).get("name") or "chain"
        # Graph state is large and mostly the queue; the useful part is which
        # chunk this is, which the metadata already carries.
        self._open(run_id, parent_run_id, str(name), "chain", None, metadata)

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, error=str(error))

    # -- models -------------------------------------------------------------

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
        name = kwargs.get("name") or (serialized or {}).get("name") or "llm"
        self._last_llm = str(run_id)
        self._open(run_id, parent_run_id, str(name), "llm", {"prompts": prompts}, metadata)

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
        name = kwargs.get("name") or (serialized or {}).get("name") or "chat"
        self._last_llm = str(run_id)
        self._open(run_id, parent_run_id, str(name), "llm", {"messages": _messages(messages)}, metadata)

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
        self._open(run_id, parent_run_id, str(name), "tool", inputs or input_str, metadata)

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, outputs=output)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, error=str(error))

    # -- tools called outside LangChain --------------------------------------

    def record_tool(self, *, name: str, args: Any, result: Any, started_at: float) -> None:
        """A completed MCP call, filed under the model call that requested it.

        The tool-gathering loop drives the session directly, so nothing else
        would record these -- and the tool calls are the part of a trace people
        actually came to read.
        """
        try:
            span_id = f"{self._last_llm or 'run'}-tool-{self.store.next_seq()}"
            self.store.start(
                span_id=span_id,
                parent_id=self._last_llm,
                name=name,
                kind="tool",
                started_at=started_at,
                inputs=args,
            )
            self.store.finish(span_id=span_id, ended_at=time.time(), outputs=result)
        except Exception as err:  # noqa: BLE001
            log.debug("tool span failed: %s", err)
