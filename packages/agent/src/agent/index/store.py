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
import threading
from types import TracebackType
from typing import Any, Iterable, Iterator, Sequence

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from ..config import AgentConfig
from ..db import Chunk as ChunkRow
from ..db import Finding as FindingRow
from ..db import Inspected as InspectedRow
from ..db import Link as LinkRow
from ..db import Note as NoteRow
from ..db import Run as RunRow
from ..db import session_factory
from .chunk import Chunk
from .links import Link

def _row_to_chunk(row: ChunkRow) -> Chunk:
    """A row to the dataclass the rest of the package passes around.

    The four list fields were JSON in a TEXT column and are real arrays now, so
    the `_loads` helper that used to sit here is gone -- the driver hands back a
    list and the dataclass wants a tuple.
    """
    return Chunk(
        chunk_id=row.chunk_id,
        file=row.file,
        symbol=row.symbol,
        kind=row.kind,
        start_line=row.start_line,
        end_line=row.end_line,
        start_byte=row.start_byte,
        end_byte=row.end_byte,
        body=row.body,
        language=row.language,
        defines=tuple(row.defines or ()),
        references=tuple(row.refs or ()),
        types_used=tuple(row.types_used or ()),
        includes=tuple(row.includes or ()),
        body_is_verbatim=bool(row.verbatim),
    )


class ChunkStore:
    """The per-run index. Use as a context manager.

    Scoped by ``run_id`` rather than by owning a file. Every statement carries
    it, which is what makes "delete the run" a cascade rather than a directory
    removal, and what lets the results cache be shared across runs while the
    index is not.
    """

    def __init__(self, run_id: str, config: AgentConfig | None = None) -> None:
        self.run_id = run_id
        self._sessions = session_factory(config)
        # Reentrant: `definition_of` and friends are built out of other methods,
        # and a plain lock would deadlock on the second one. Kept even though
        # the pool is thread-safe, because `uninspected()` reads twice and must
        # not see a write land between them.
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
        """Nothing to close: sessions are per-operation. Kept because callers
        pair it with the constructor and with `__exit__`."""

    def _mine(self, model: Any) -> Any:
        return model.run_id == self.run_id

    # -- writing -----------------------------------------------------------

    def add_chunks(self, chunks: Iterable[Chunk]) -> None:
        rows = [
            {
                "run_id": self.run_id,
                "chunk_id": c.chunk_id,
                "file": c.file,
                "symbol": c.symbol,
                "kind": c.kind,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "start_byte": c.start_byte,
                "end_byte": c.end_byte,
                "body": c.body,
                "language": c.language,
                "defines": list(c.defines),
                "refs": list(c.references),
                "types_used": list(c.types_used),
                "includes": list(c.includes),
                "verbatim": bool(c.body_is_verbatim),
            }
            for c in chunks
        ]
        if not rows:
            return
        with self.lock, self._sessions() as session:
            statement = insert(ChunkRow)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["run_id", "chunk_id"],
                    set_={k: statement.excluded[k] for k in rows[0] if k not in ("run_id", "chunk_id")},
                ),
                rows,
            )
            session.commit()

    def add_links(self, links: Iterable[Link]) -> None:
        rows = [
            {"run_id": self.run_id, "src": link.src, "dst": link.dst, "kind": link.kind, "symbol": link.symbol}
            for link in links
        ]
        if not rows:
            return
        with self.lock, self._sessions() as session:
            session.execute(insert(LinkRow).on_conflict_do_nothing(), rows)
            session.commit()

    def set_order(self, chunk_ids: Sequence[str]) -> None:
        self.set_meta("order", json.dumps(list(chunk_ids)))

    def set_levels(self, levels: dict[str, int]) -> None:
        """Which chunks may be inspected together. See :func:`agent.index.order.call_levels`."""
        self.set_meta("levels", json.dumps(levels, sort_keys=True))

    def set_meta(self, key: str, value: str) -> None:
        """Index metadata, on the run row.

        Was a `meta` key/value table per index database. There is one run row
        already carrying free-form metadata, so this writes into it under
        `index.<key>` rather than adding a table whose only job is two keys.
        """
        with self.lock, self._sessions() as session:
            row = session.get(RunRow, self.run_id)
            if row is None:
                return
            meta = dict(row.meta or {})
            index_meta = dict(meta.get("_index") or {})
            index_meta[key] = value
            meta["_index"] = index_meta
            row.meta = meta
            session.commit()

    def set_note(self, chunk_id: str, note: str) -> None:
        with self.lock, self._sessions() as session:
            statement = insert(NoteRow).values(run_id=self.run_id, chunk_id=chunk_id, note=note)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["run_id", "chunk_id"], set_={"note": note}
                )
            )
            session.commit()

    def mark_inspected(self, chunk_id: str) -> None:
        with self.lock, self._sessions() as session:
            session.execute(
                insert(InspectedRow)
                .values(run_id=self.run_id, chunk_id=chunk_id)
                .on_conflict_do_nothing()
            )
            session.commit()

    def add_findings(self, chunk_id: str, findings: Iterable[dict[str, Any]]) -> None:
        rows = [
            {
                "run_id": self.run_id,
                "id": f["id"],
                "chunk_id": chunk_id,
                "file": f["primary"]["file"],
                "payload": f,
            }
            for f in findings
        ]
        if not rows:
            return
        with self.lock, self._sessions() as session:
            statement = insert(FindingRow)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["run_id", "id"],
                    set_={
                        "chunk_id": statement.excluded.chunk_id,
                        "file": statement.excluded.file,
                        "payload": statement.excluded.payload,
                    },
                ),
                rows,
            )
            session.commit()

    # -- clearing ------------------------------------------------------------
    #
    # Here rather than as raw SQL at the call site: the API was reaching into
    # `store.conn` to do these, which put statements that have to agree with the
    # schema three files away from it.

    def clear_index(self) -> None:
        """Drop the chunks and links, for a re-index of the same run."""
        with self.lock, self._sessions() as session:
            session.execute(delete(ChunkRow).where(self._mine(ChunkRow)))
            session.execute(delete(LinkRow).where(self._mine(LinkRow)))
            session.commit()

    def clear_results(self) -> None:
        """Forget every inspection, so a forced run does the work again."""
        with self.lock, self._sessions() as session:
            session.execute(delete(InspectedRow).where(self._mine(InspectedRow)))
            session.execute(delete(FindingRow).where(self._mine(FindingRow)))
            session.commit()

    def drop_findings_in_file(self, file: str) -> None:
        with self.lock, self._sessions() as session:
            session.execute(delete(FindingRow).where(self._mine(FindingRow), FindingRow.file == file))
            session.commit()

    # -- reading -----------------------------------------------------------

    def _chunks(self, *where: Any, order: Any = None) -> list[Chunk]:
        query = select(ChunkRow).where(self._mine(ChunkRow), *where)
        query = query.order_by(*(order or (ChunkRow.file, ChunkRow.start_line)))
        with self.lock, self._sessions() as session:
            return [_row_to_chunk(row) for row in session.scalars(query)]

    def get_meta(self, key: str) -> str | None:
        with self.lock, self._sessions() as session:
            row = session.get(RunRow, self.run_id)
            value = ((row.meta or {}).get("_index") or {}).get(key) if row else None
        return str(value) if value is not None else None

    def order(self) -> list[str]:
        raw = self.get_meta("order")
        if raw is None:
            return [chunk.chunk_id for chunk in self._chunks()]
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
        found = self._chunks(ChunkRow.chunk_id == chunk_id)
        return found[0] if found else None

    def chunks(self) -> Iterator[Chunk]:
        yield from self._chunks()

    def chunks_in_file(self, file: str) -> list[Chunk]:
        return self._chunks(ChunkRow.file == file, order=(ChunkRow.start_line,))

    def files(self) -> list[str]:
        with self.lock, self._sessions() as session:
            return list(
                session.scalars(
                    select(ChunkRow.file).where(self._mine(ChunkRow)).distinct().order_by(ChunkRow.file)
                )
            )

    def links(self) -> list[Link]:
        with self.lock, self._sessions() as session:
            rows = session.scalars(
                select(LinkRow)
                .where(self._mine(LinkRow))
                .order_by(LinkRow.src, LinkRow.kind, LinkRow.symbol, LinkRow.dst)
            )
            return [Link(src=r.src, dst=r.dst, kind=r.kind, symbol=r.symbol) for r in rows]

    def callees_of(self, chunk_id: str, kind: str = "calls") -> list[Chunk]:
        return self._related(chunk_id, kind, LinkRow.src, LinkRow.dst)

    def callers_of(self, chunk_id: str, kind: str = "calls") -> list[Chunk]:
        return self._related(chunk_id, kind, LinkRow.dst, LinkRow.src)

    def _related(self, chunk_id: str, kind: str, anchor: Any, other: Any) -> list[Chunk]:
        """Both directions of the same join, which is all callers/callees are."""
        query = (
            select(ChunkRow)
            .join(LinkRow, (LinkRow.run_id == ChunkRow.run_id) & (other == ChunkRow.chunk_id))
            .where(self._mine(ChunkRow), anchor == chunk_id, LinkRow.kind == kind)
            .order_by(ChunkRow.file, ChunkRow.start_line)
        )
        with self.lock, self._sessions() as session:
            return [_row_to_chunk(row) for row in session.scalars(query)]

    def note(self, chunk_id: str) -> str | None:
        with self.lock, self._sessions() as session:
            return session.scalar(
                select(NoteRow.note).where(self._mine(NoteRow), NoteRow.chunk_id == chunk_id)
            )

    def is_inspected(self, chunk_id: str) -> bool:
        with self.lock, self._sessions() as session:
            return (
                session.scalar(
                    select(InspectedRow.chunk_id).where(
                        self._mine(InspectedRow), InspectedRow.chunk_id == chunk_id
                    )
                )
                is not None
            )

    def uninspected(self) -> list[str]:
        """Chunks with no stored result, in the order a run would take them.

        A chunk id is derived from its content, so a tree that has not changed
        since the last run has none of these -- and a run started over it would
        call no model, find nothing, and still reset the record of the run that
        did. Asking first is what lets the caller decline.
        """
        with self.lock:
            with self._sessions() as session:
                done = set(
                    session.scalars(
                        select(InspectedRow.chunk_id).where(self._mine(InspectedRow))
                    )
                )
            return [chunk_id for chunk_id in self.order() if chunk_id not in done]

    def findings(self) -> list[dict[str, Any]]:
        with self.lock, self._sessions() as session:
            return list(
                session.scalars(
                    select(FindingRow.payload)
                    .where(self._mine(FindingRow))
                    .order_by(FindingRow.file, FindingRow.id)
                )
            )

    def findings_for_chunk(self, chunk_id: str) -> list[dict[str, Any]]:
        with self.lock, self._sessions() as session:
            return list(
                session.scalars(
                    select(FindingRow.payload).where(
                        self._mine(FindingRow), FindingRow.chunk_id == chunk_id
                    )
                )
            )

    def definition_of(self, symbol: str) -> list[Chunk]:
        """Chunks defining a symbol.

        A containment test on the array rather than loading every chunk and
        filtering in Python, which is what the JSON-in-TEXT column forced.
        """
        return self._chunks(ChunkRow.defines.any(symbol))
