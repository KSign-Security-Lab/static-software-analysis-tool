"""Per-run SQLite store: chunks, links, notes, findings.

On disk rather than in memory because a run has to survive the process, and
because it is what makes incremental re-inspection possible. One file per run,
at ``<run_dir>/index.db``.
"""

from __future__ import annotations

import json
import sqlite3
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
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self.conn.commit()

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
        self.conn.close()

    # -- writing -----------------------------------------------------------

    def add_chunks(self, chunks: Iterable[Chunk]) -> None:
        self.conn.executemany(
            """INSERT OR REPLACE INTO chunks
               (chunk_id, file, symbol, kind, start_line, end_line, start_byte,
                end_byte, body, language, defines, refs, types_used, includes,
                verbatim)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
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
            ],
        )
        self.conn.commit()

    def add_links(self, links: Iterable[Link]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO links (src, dst, kind, symbol) VALUES (?,?,?,?)",
            [(link.src, link.dst, link.kind, link.symbol) for link in links],
        )
        self.conn.commit()

    def set_order(self, chunk_ids: Sequence[str]) -> None:
        self.set_meta("order", json.dumps(list(chunk_ids)))

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
        self.conn.commit()

    def set_note(self, chunk_id: str, note: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO notes (chunk_id, note) VALUES (?,?)", (chunk_id, note))
        self.conn.commit()

    def mark_inspected(self, chunk_id: str) -> None:
        self.conn.execute("INSERT OR REPLACE INTO inspected (chunk_id) VALUES (?)", (chunk_id,))
        self.conn.commit()

    def add_findings(self, chunk_id: str, findings: Iterable[dict[str, Any]]) -> None:
        self.conn.executemany(
            "INSERT OR REPLACE INTO findings (id, chunk_id, file, payload) VALUES (?,?,?,?)",
            [(f["id"], chunk_id, f["primary"]["file"], json.dumps(f)) for f in findings],
        )
        self.conn.commit()

    # -- reading -----------------------------------------------------------

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(row["value"]) if row else None

    def order(self) -> list[str]:
        raw = self.get_meta("order")
        if raw is None:
            return [
                row["chunk_id"] for row in self.conn.execute("SELECT chunk_id FROM chunks ORDER BY file, start_line")
            ]
        parsed: list[str] = json.loads(raw)
        return parsed

    def chunk(self, chunk_id: str) -> Chunk | None:
        row = self.conn.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
        return _row_to_chunk(row) if row else None

    def chunks(self) -> Iterator[Chunk]:
        for row in self.conn.execute("SELECT * FROM chunks ORDER BY file, start_line"):
            yield _row_to_chunk(row)

    def chunks_in_file(self, file: str) -> list[Chunk]:
        rows = self.conn.execute("SELECT * FROM chunks WHERE file = ? ORDER BY start_line", (file,))
        return [_row_to_chunk(row) for row in rows]

    def files(self) -> list[str]:
        return [row["file"] for row in self.conn.execute("SELECT DISTINCT file FROM chunks ORDER BY file")]

    def links(self) -> list[Link]:
        rows = self.conn.execute("SELECT * FROM links ORDER BY src, kind, symbol, dst")
        return [Link(src=r["src"], dst=r["dst"], kind=r["kind"], symbol=r["symbol"]) for r in rows]

    def callees_of(self, chunk_id: str, kind: str = "calls") -> list[Chunk]:
        rows = self.conn.execute(
            """SELECT c.* FROM links l JOIN chunks c ON c.chunk_id = l.dst
               WHERE l.src = ? AND l.kind = ? ORDER BY c.file, c.start_line""",
            (chunk_id, kind),
        )
        return [_row_to_chunk(row) for row in rows]

    def callers_of(self, chunk_id: str, kind: str = "calls") -> list[Chunk]:
        rows = self.conn.execute(
            """SELECT c.* FROM links l JOIN chunks c ON c.chunk_id = l.src
               WHERE l.dst = ? AND l.kind = ? ORDER BY c.file, c.start_line""",
            (chunk_id, kind),
        )
        return [_row_to_chunk(row) for row in rows]

    def note(self, chunk_id: str) -> str | None:
        row = self.conn.execute("SELECT note FROM notes WHERE chunk_id = ?", (chunk_id,)).fetchone()
        return str(row["note"]) if row else None

    def is_inspected(self, chunk_id: str) -> bool:
        return self.conn.execute("SELECT 1 FROM inspected WHERE chunk_id = ?", (chunk_id,)).fetchone() is not None

    def findings(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT payload FROM findings ORDER BY file, id")
        return [json.loads(row["payload"]) for row in rows]

    def findings_for_chunk(self, chunk_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT payload FROM findings WHERE chunk_id = ?", (chunk_id,))
        return [json.loads(row["payload"]) for row in rows]

    def definition_of(self, symbol: str) -> list[Chunk]:
        """Chunks defining a symbol."""
        rows = self.conn.execute("SELECT * FROM chunks ORDER BY file, start_line")
        return [chunk for chunk in map(_row_to_chunk, rows) if symbol in chunk.defines]
