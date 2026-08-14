"""Spans, recorded locally.

An inspection is a tree of calls -- graph node, LLM, tool -- and after it
finishes the only record was a number in the stats. Reconstructing why a finding
was refuted meant reading the source and guessing.

Kept in the same database as the run's chunks and findings, scoped by `run_id`
and cascading from the run row -- so a trace lives and dies with the run it
describes and nothing leaves the machine. LangSmith does the same job when it is
configured; this works when it is not, which is the normal case here.
"""

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

#: Prompts and completions are long. A trace has to be readable more than it has
#: to be complete, and the whole point is to skim it.
MAX_PAYLOAD = 20_000


def clip(value: Any) -> str | None:
    """Serialise a payload, bounded."""
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
        # Rounded, not truncated: float subtraction turns a clean 0.4s into
        # 0.3999..., and truncating reports it as 399ms.
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
            # When it started, not only how long it took. With the specialists
            # on one chunk, a list of durations cannot say whether they ran
            # together or one after another -- and that is the thing worth
            # seeing. The trace draws them against the wall clock.
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
    """Span rows for one run.

    Callbacks fire from whichever thread is running the step -- the graph
    thread, and for tools the MCP session's loop thread -- so writes are
    serialised behind a lock. Each one is its own short transaction, which is
    the point: a trace is written *as the run happens*, and a reader watching it
    must see steps land rather than nothing until the run ends.

    Scoped to a run by ``run_id`` rather than by having its own file. That is
    what makes `seq` a per-run sequence and not a global one.
    """

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
        """Nothing to close. Sessions are per-operation and already returned to
        the pool; the method stays because callers pair it with `spans()`."""

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
        # seq preserves arrival order, which is what makes the tree render in
        # the order things actually happened rather than by id.
        with self._lock:
            seq = self._seq
            self._seq += 1
        with self._sessions() as session:
            # Upsert, because a retried step reuses its span id -- which is how
            # `attempts` is counted downstream.
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
