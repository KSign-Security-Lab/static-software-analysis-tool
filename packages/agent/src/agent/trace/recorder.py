from __future__ import annotations

import logging
import threading
import time
from contextvars import ContextVar
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
    if parent is None:
        return True
    node = (metadata or {}).get("langgraph_node")
    return bool(node) and given == node


_open_llm: ContextVar[str | None] = ContextVar("agent_trace_open_llm", default=None)


class SpanRecorder(BaseCallbackHandler):
    def __init__(self, store: SpanStore) -> None:
        self.store = store
        self._skipped: dict[str, str | None] = {}
        self._label: dict[str, str] = {}
        self._lock = threading.Lock()

    @property
    def _last_llm(self) -> str | None:
        return _open_llm.get()

    @_last_llm.setter
    def _last_llm(self, span_id: str | None) -> None:
        _open_llm.set(span_id)

    def _parent_of(self, parent: UUID | None) -> str | None:
        current = str(parent) if parent else None
        seen = 0
        with self._lock:
            while current in self._skipped and seen < 20:
                current = self._skipped[current]
                seen += 1
        return current

    def _inherited(self, parent: UUID | None) -> str | None:
        current = str(parent) if parent else None
        seen = 0
        with self._lock:
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
        with self._lock:
            if str(run_id) in self._skipped:
                return
        try:
            self.store.finish(span_id=str(run_id), ended_at=time.time(), outputs=outputs, tokens=tokens, error=error)
        except Exception as err:  # noqa: BLE001
            log.debug("span finish failed: %s", err)

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
            parent = self._parent_of(parent_run_id)
            with self._lock:
                self._skipped[str(run_id)] = parent
                if given:
                    self._label[str(run_id)] = str(given)
            return
        self._open(run_id, self._parent_of(parent_run_id), str(given or "chain"), "chain", None, metadata)

    def on_chain_end(self, outputs: dict[str, Any], *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id)

    def on_chain_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, error=str(error))

    def _model_name(self, serialized: dict[str, Any], parent: UUID | None, kwargs: dict[str, Any]) -> str:
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
        parent = self._last_llm or self._parent_of(parent_run_id)
        self._open(run_id, parent, str(name), "tool", inputs or input_str, metadata)

    def on_tool_end(self, output: Any, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, outputs=output)

    def on_tool_error(self, error: BaseException, *, run_id: UUID, **kwargs: Any) -> None:
        self._close(run_id, error=str(error))
