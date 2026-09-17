from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from ..config import AgentConfig
from ..db import Span as SpanRow
from ..db import session_factory

MAX_PAYLOAD = 20_000


def clip(value: Any) -> str | None:
    if value is None:
        return None
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError, ValueError:
        text = str(value)
    if len(text) <= MAX_PAYLOAD:
        return text
    return json.dumps({"_truncated": True, "_chars": len(text), "preview": text[:MAX_PAYLOAD]})


@dataclass(frozen=True)
class Span:
    id: str
    parent_id: str | None
    seq: int
    name: str
    kind: str
    started_at: float
    ended_at: float | None
    status: str
    error: str | None
    inputs: Any
    outputs: Any
    tokens: int | None
    meta: dict[str, Any]

    @property
    def latency_ms(self) -> int | None:
        if self.ended_at is None:
            return None
        return round((self.ended_at - self.started_at) * 1000)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "seq": self.seq,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "error": self.error,
            "started_at": self.started_at,
            "latency_ms": self.latency_ms,
            "tokens": self.tokens,
            "meta": self.meta,
            "inputs": self.inputs,
            "outputs": self.outputs,
        }


def _load(raw: str | None) -> Any:
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


class SpanStore:
    def __init__(self, run_id: str, config: AgentConfig | None = None) -> None:
        self.run_id = run_id
        self._sessions = session_factory(config)
        self._lock = threading.Lock()
        self._seq = self._next_seq()

    def _next_seq(self) -> int:
        with self._sessions() as session:
            highest = session.scalar(
                select(func.max(SpanRow.seq)).where(SpanRow.run_id == self.run_id)
            )
        return int(highest or 0) + 1

    def close(self) -> None:
        pass

    def start(
        self,
        *,
        span_id: str,
        parent_id: str | None,
        name: str,
        kind: str,
        started_at: float,
        inputs: Any = None,
        meta: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            seq = self._seq
            self._seq += 1
        with self._sessions() as session:
            session.execute(
                insert(SpanRow)
                .values(
                    run_id=self.run_id,
                    id=span_id,
                    parent_id=parent_id,
                    seq=seq,
                    name=name,
                    kind=kind,
                    started_at=started_at,
                    status="running",
                    inputs=clip(inputs),
                    meta=json.dumps(meta or {}),
                )
                .on_conflict_do_update(
                    index_elements=["run_id", "id"],
                    set_={
                        "parent_id": parent_id,
                        "seq": seq,
                        "name": name,
                        "kind": kind,
                        "started_at": started_at,
                        "status": "running",
                        "inputs": clip(inputs),
                        "meta": json.dumps(meta or {}),
                    },
                )
            )
            session.commit()

    def finish(
        self,
        *,
        span_id: str,
        ended_at: float,
        outputs: Any = None,
        tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        with self._sessions() as session:
            session.execute(
                update(SpanRow)
                .where(SpanRow.run_id == self.run_id, SpanRow.id == span_id)
                .values(
                    ended_at=ended_at,
                    status="error" if error else "ok",
                    outputs=clip(outputs),
                    tokens=tokens,
                    error=error,
                )
            )
            session.commit()

    def spans(self) -> list[Span]:
        with self._sessions() as session:
            rows = list(
                session.scalars(
                    select(SpanRow).where(SpanRow.run_id == self.run_id).order_by(SpanRow.seq)
                )
            )
        return [
            Span(
                id=r.id,
                parent_id=r.parent_id,
                seq=r.seq,
                name=r.name,
                kind=r.kind,
                started_at=r.started_at,
                ended_at=r.ended_at,
                status=r.status,
                error=r.error,
                inputs=_load(r.inputs),
                outputs=_load(r.outputs),
                tokens=r.tokens,
                meta=_load(r.meta) or {},
            )
            for r in rows
        ]

    def clear(self) -> None:
        with self._sessions() as session:
            session.execute(delete(SpanRow).where(SpanRow.run_id == self.run_id))
            session.commit()
        with self._lock:
            self._seq = 1
