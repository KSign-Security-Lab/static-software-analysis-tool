"""Spans, recorded locally.

An inspection is a tree of calls -- graph node, LLM, tool -- and after it
finishes the only record was a number in the stats. Reconstructing why a finding
was refuted meant reading the source and guessing.

Kept in the run's own SQLite next to its chunks and findings, so a trace lives
and dies with the run it describes and nothing leaves the machine. LangSmith
does the same job when it is configured; this works when it is not, which is the
normal case here.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS spans (
    id          TEXT PRIMARY KEY,
    parent_id   TEXT,
    seq         INTEGER NOT NULL,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    started_at  REAL NOT NULL,
    ended_at    REAL,
    status      TEXT NOT NULL,
    error       TEXT,
    inputs      TEXT,
    outputs     TEXT,
    tokens      INTEGER,
    meta        TEXT
);
CREATE INDEX IF NOT EXISTS spans_parent ON spans(parent_id);
CREATE INDEX IF NOT EXISTS spans_seq ON spans(seq);
"""

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
        if self.ended_at is None:
            return None
        return int((self.ended_at - self.started_at) * 1000)

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "parent_id": self.parent_id,
            "seq": self.seq,
            "name": self.name,
            "kind": self.kind,
            "status": self.status,
            "error": self.error,
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
    thread, and for tools the MCP session's loop thread -- so the connection is
    shared across threads behind a lock rather than confined to one.
    """

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self._lock = threading.Lock()
        self._seq = self._next_seq()

    def _next_seq(self) -> int:
        row = self.conn.execute("SELECT MAX(seq) AS m FROM spans").fetchone()
        return int((row["m"] or 0)) + 1

    def next_seq(self) -> int:
        """The seq the next :meth:`start` will use -- for callers that have to
        mint their own span id."""
        with self._lock:
            return self._seq

    def close(self) -> None:
        with self._lock:
            self.conn.close()

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
            self.conn.execute(
                """INSERT OR REPLACE INTO spans
                   (id, parent_id, seq, name, kind, started_at, status, inputs, meta)
                   VALUES (?,?,?,?,?,?,'running',?,?)""",
                (span_id, parent_id, self._seq, name, kind, started_at, clip(inputs), json.dumps(meta or {})),
            )
            self._seq += 1
            self.conn.commit()

    def finish(
        self,
        *,
        span_id: str,
        ended_at: float,
        outputs: Any = None,
        tokens: int | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            self.conn.execute(
                """UPDATE spans SET ended_at = ?, status = ?, outputs = ?, tokens = ?, error = ?
                   WHERE id = ?""",
                (ended_at, "error" if error else "ok", clip(outputs), tokens, error, span_id),
            )
            self.conn.commit()

    def spans(self) -> list[Span]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM spans ORDER BY seq").fetchall()
        return [
            Span(
                id=r["id"],
                parent_id=r["parent_id"],
                seq=r["seq"],
                name=r["name"],
                kind=r["kind"],
                started_at=r["started_at"],
                ended_at=r["ended_at"],
                status=r["status"],
                error=r["error"],
                inputs=_load(r["inputs"]),
                outputs=_load(r["outputs"]),
                tokens=r["tokens"],
                meta=_load(r["meta"]) or {},
            )
            for r in rows
        ]

    def clear(self) -> None:
        with self._lock:
            self.conn.execute("DELETE FROM spans")
            self.conn.commit()
            self._seq = 1
