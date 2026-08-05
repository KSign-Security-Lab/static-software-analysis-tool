"""Per-run SQLite store: chunks, links, notes, findings.

On disk rather than in memory because a run has to survive the process, and
because it is what makes incremental re-inspection possible. One file per run,
at ``<run_dir>/index.db``.

Shared between threads. The inspection used to be one node at a time on one
thread, so a connection bound to its creator was fine; now a wave of chunks runs
concurrently on LangGraph's pool and every one of them reads and writes here.
``check_same_thread=False`` plus a lock is the same arrangement
:mod:`agent.trace.store` already uses, for the same reason.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from types import TracebackType
from typing import Any, Iterable, Iterator, Sequence

from .chunk import Chunk
from .links import Link

SCHEMA = """
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id   TEXT PRIMARY KEY,
    file       TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    kind       TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line   INTEGER NOT NULL,
    start_byte INTEGER NOT NULL,
    end_byte   INTEGER NOT NULL,
    body       TEXT NOT NULL,
    language   TEXT NOT NULL,
    defines    TEXT NOT NULL,
    refs       TEXT NOT NULL,
    types_used TEXT NOT NULL,
    includes   TEXT NOT NULL,
    verbatim   INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS chunks_file ON chunks(file);

CREATE TABLE IF NOT EXISTS links (
    src    TEXT NOT NULL,
    dst    TEXT NOT NULL,
    kind   TEXT NOT NULL,
    symbol TEXT NOT NULL,
    PRIMARY KEY (src, dst, kind, symbol)
);
CREATE INDEX IF NOT EXISTS links_src ON links(src);
CREATE INDEX IF NOT EXISTS links_dst ON links(dst);

-- Cross-chunk metadata: what a callee concluded, for its callers.
CREATE TABLE IF NOT EXISTS notes (
    chunk_id TEXT PRIMARY KEY,
    note     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS findings (
    id       TEXT PRIMARY KEY,
    chunk_id TEXT NOT NULL,
    file     TEXT NOT NULL,
    payload  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS findings_chunk ON findings(chunk_id);

-- So a re-run can tell "no findings" from "not yet analysed".
CREATE TABLE IF NOT EXISTS inspected (
    chunk_id TEXT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _loads(raw: str) -> tuple[str, ...]:
    parsed: list[str] = json.loads(raw)
    return tuple(parsed)


def _row_to_chunk(row: sqlite3.Row) -> Chunk:
    return Chunk(
        chunk_id=row["chunk_id"],
        file=row["file"],
        symbol=row["symbol"],
        kind=row["kind"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        start_byte=row["start_byte"],
        end_byte=row["end_byte"],
        body=row["body"],
        language=row["language"],
        defines=_loads(row["defines"]),
        references=_loads(row["refs"]),
        types_used=_loads(row["types_used"]),
        includes=_loads(row["includes"]),
        body_is_verbatim=bool(row["verbatim"]),
    )


class ChunkStore:
    """The per-run index. Use as a context manager."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        # WAL so `GET /findings` can read while the inspection thread writes.
        # The default rollback journal makes them block each other, which under
        # a slower disk shows up as "database is locked".
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        # Reentrant: `definition_of` and friends are built out of other methods,
        # and a plain lock would deadlock on the second one.
        self.lock = threading.RLock()

    def __enter__(self) -> ChunkStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        with self.lock:
            self.conn.close()

    # -- writing -----------------------------------------------------------

    def add_chunks(self, chunks: Iterable[Chunk]) -> None:
        rows = [
            (
                c.chunk_id,
                c.file,
                c.symbol,
                c.kind,
                c.start_line,
                c.end_line,
                c.start_byte,
                c.end_byte,
                c.body,
                c.language,
                json.dumps(list(c.defines)),
                json.dumps(list(c.references)),
                json.dumps(list(c.types_used)),
                json.dumps(list(c.includes)),
                int(c.body_is_verbatim),
            )
            for c in chunks
        ]
        with self.lock:
            self.conn.executemany(
                """INSERT OR REPLACE INTO chunks
                   (chunk_id, file, symbol, kind, start_line, end_line, start_byte,
                    end_byte, body, language, defines, refs, types_used, includes,
                    verbatim)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            self.conn.commit()

    def add_links(self, links: Iterable[Link]) -> None:
        rows = [(link.src, link.dst, link.kind, link.symbol) for link in links]
        with self.lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO links (src, dst, kind, symbol) VALUES (?,?,?,?)",
                rows,
            )
            self.conn.commit()

    def set_order(self, chunk_ids: Sequence[str]) -> None:
        self.set_meta("order", json.dumps(list(chunk_ids)))

    def set_levels(self, levels: dict[str, int]) -> None:
        """Which chunks may be inspected together. See :func:`agent.index.order.call_levels`."""
        self.set_meta("levels", json.dumps(levels, sort_keys=True))

    def set_meta(self, key: str, value: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
            self.conn.commit()

    def set_note(self, chunk_id: str, note: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO notes (chunk_id, note) VALUES (?,?)", (chunk_id, note))
            self.conn.commit()

    def mark_inspected(self, chunk_id: str) -> None:
        with self.lock:
            self.conn.execute("INSERT OR REPLACE INTO inspected (chunk_id) VALUES (?)", (chunk_id,))
            self.conn.commit()

    def add_findings(self, chunk_id: str, findings: Iterable[dict[str, Any]]) -> None:
        rows = [(f["id"], chunk_id, f["primary"]["file"], json.dumps(f)) for f in findings]
        with self.lock:
            self.conn.executemany(
                "INSERT OR REPLACE INTO findings (id, chunk_id, file, payload) VALUES (?,?,?,?)",
                rows,
            )
            self.conn.commit()

    # -- clearing ------------------------------------------------------------
    #
    # Here rather than as raw SQL at the call site: the API was reaching into
    # `store.conn` to do these, which put statements that have to agree with the
    # schema three files away from it.

    def clear_index(self) -> None:
        """Drop the chunks and links, for a re-index of the same run."""
        with self.lock:
            self.conn.execute("DELETE FROM chunks")
            self.conn.execute("DELETE FROM links")
            self.conn.commit()

    def clear_results(self) -> None:
        """Forget every inspection, so a forced run does the work again."""
        with self.lock:
            self.conn.execute("DELETE FROM inspected")
            self.conn.execute("DELETE FROM findings")
            self.conn.commit()

    def drop_findings_in_file(self, file: str) -> None:
        with self.lock:
            self.conn.execute("DELETE FROM findings WHERE file = ?", (file,))
            self.conn.commit()

    # -- reading -----------------------------------------------------------

    def _rows(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        """Read under the lock and materialise.

        Materialised rather than handing back a cursor: a caller that iterated
        lazily would be reading the connection from wherever it happened to be,
        which is exactly what the lock is here to prevent.
        """
        with self.lock:
            return list(self.conn.execute(sql, tuple(params)))

    def get_meta(self, key: str) -> str | None:
        rows = self._rows("SELECT value FROM meta WHERE key = ?", (key,))
        return str(rows[0]["value"]) if rows else None

    def order(self) -> list[str]:
        raw = self.get_meta("order")
        if raw is None:
            return [row["chunk_id"] for row in self._rows("SELECT chunk_id FROM chunks ORDER BY file, start_line")]
        parsed: list[str] = json.loads(raw)
        return parsed

    def levels(self) -> dict[str, int]:
        """Chunk id to call depth; empty for an index written before levels existed."""
        raw = self.get_meta("levels")
        if raw is None:
            return {}
        parsed: dict[str, int] = json.loads(raw)
        return parsed

    def chunk(self, chunk_id: str) -> Chunk | None:
        rows = self._rows("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,))
        return _row_to_chunk(rows[0]) if rows else None

    def chunks(self) -> Iterator[Chunk]:
        for row in self._rows("SELECT * FROM chunks ORDER BY file, start_line"):
            yield _row_to_chunk(row)

    def chunks_in_file(self, file: str) -> list[Chunk]:
        rows = self._rows("SELECT * FROM chunks WHERE file = ? ORDER BY start_line", (file,))
        return [_row_to_chunk(row) for row in rows]

    def files(self) -> list[str]:
        return [row["file"] for row in self._rows("SELECT DISTINCT file FROM chunks ORDER BY file")]

    def links(self) -> list[Link]:
        rows = self._rows("SELECT * FROM links ORDER BY src, kind, symbol, dst")
        return [Link(src=r["src"], dst=r["dst"], kind=r["kind"], symbol=r["symbol"]) for r in rows]

    def callees_of(self, chunk_id: str, kind: str = "calls") -> list[Chunk]:
        rows = self._rows(
            """SELECT c.* FROM links l JOIN chunks c ON c.chunk_id = l.dst
               WHERE l.src = ? AND l.kind = ? ORDER BY c.file, c.start_line""",
            (chunk_id, kind),
        )
        return [_row_to_chunk(row) for row in rows]

    def callers_of(self, chunk_id: str, kind: str = "calls") -> list[Chunk]:
        rows = self._rows(
            """SELECT c.* FROM links l JOIN chunks c ON c.chunk_id = l.src
               WHERE l.dst = ? AND l.kind = ? ORDER BY c.file, c.start_line""",
            (chunk_id, kind),
        )
        return [_row_to_chunk(row) for row in rows]

    def note(self, chunk_id: str) -> str | None:
        rows = self._rows("SELECT note FROM notes WHERE chunk_id = ?", (chunk_id,))
        return str(rows[0]["note"]) if rows else None

    def is_inspected(self, chunk_id: str) -> bool:
        return bool(self._rows("SELECT 1 FROM inspected WHERE chunk_id = ?", (chunk_id,)))

    def findings(self) -> list[dict[str, Any]]:
        rows = self._rows("SELECT payload FROM findings ORDER BY file, id")
        return [json.loads(row["payload"]) for row in rows]

    def findings_for_chunk(self, chunk_id: str) -> list[dict[str, Any]]:
        rows = self._rows("SELECT payload FROM findings WHERE chunk_id = ?", (chunk_id,))
        return [json.loads(row["payload"]) for row in rows]

    def definition_of(self, symbol: str) -> list[Chunk]:
        """Chunks defining a symbol."""
        rows = self._rows("SELECT * FROM chunks ORDER BY file, start_line")
        return [chunk for chunk in map(_row_to_chunk, rows) if symbol in chunk.defines]
