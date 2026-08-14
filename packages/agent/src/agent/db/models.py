"""One run, one row, and everything it owns hanging off it.

A run used to be a directory holding three SQLite databases, three JSON files
and an extracted source tree -- seven things held together by a path
convention. Nothing could be asked across runs, no transaction spanned a run's
own state, and listing them meant reading every directory off disk.

The tables here are not new. They are the `CREATE TABLE` text that was already
in `index/store.py`, `trace/store.py`, `index/embed.py` and `cache.py`, given a
`run_id` and a foreign key. What changes is that the run is the parent: deleting
one is a single statement rather than an `rmtree`, and the cascade means no
table can outlive the run it describes.

The one deliberate exception is `results`, the cross-run cache. It is keyed by a
content-derived chunk id precisely so that a re-run of unchanged code can reuse
what a *previous* run concluded, so tying it to a run would defeat it.
"""

from __future__ import annotations

import time
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

#: `BAAI/bge-small-en-v1.5`, which is what `index/embed.py` embeds with. The
#: column is fixed-width, so this and `MODEL_NAME` have to move together.
EMBED_DIMS = 384


class Base(DeclarativeBase):
    pass


def _now() -> float:
    return time.time()


class Run(Base):
    """The run itself: status, who made it, and what it concluded."""

    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    #: A name somebody typed, not an identity. See the API's `owner` header --
    #: it exists so a shared list can be filtered to yours, and it is not a
    #: security boundary. Nullable because a run made by the CLI has no browser
    #: to have asked.
    owner: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=_now)
    updated_at: Mapped[float] = mapped_column(Float, default=_now, onupdate=_now)

    #: The report, as the pydantic model serialises it. Not shredded into
    #: columns: `agent/schema.py` owns that shape, it is versioned, and it is
    #: what goes over the wire -- a second definition here would drift from it.
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    #: What `read_meta`/`write_meta` used to keep in `meta.json`. Free-form on
    #: purpose: `write_meta(**updates)` takes arbitrary keys and several call
    #: sites rely on that.
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

    #: The tree as a graph, which used to be `graph.json`. One per run, so a
    #: column rather than a table.
    knowledge: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    files: Mapped[list[File]] = relationship(back_populates="run", cascade="all, delete-orphan")


class File(Base):
    """A file of the uploaded tree.

    Rows, not a directory, which is the whole point of this change. It also
    retires `agent/paths.py`: `resolve_within` existed to stop a hostile archive
    escaping the run root, and a path that is a column cannot escape anything.
    The archive caps in `extract_zip` stay -- a zip bomb is still a zip bomb
    when the destination is a table.
    """

    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("run_id", "path", name="files_run_path"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    #: Content hash, so a re-upload of an unchanged file is recognisable without
    #: comparing bodies.
    sha: Mapped[str] = mapped_column(String(64))

    run: Mapped[Run] = relationship(back_populates="files")


class Chunk(Base):
    """One unit of code: a function, or a file's top-level declarations."""

    __tablename__ = "chunks"
    __table_args__ = (Index("chunks_run_file", "run_id", "file"),)

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    file: Mapped[str] = mapped_column(Text)
    symbol: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32))
    start_line: Mapped[int] = mapped_column(Integer)
    end_line: Mapped[int] = mapped_column(Integer)
    start_byte: Mapped[int] = mapped_column(Integer)
    end_byte: Mapped[int] = mapped_column(Integer)
    body: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(32))

    #: These were JSON strings in a TEXT column and are arrays here, which is
    #: what they always were -- the store's `_loads` helper goes with them.
    defines: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    refs: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    types_used: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    includes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)

    #: Whether the body is the source verbatim. Was an INTEGER standing in for a
    #: boolean, because SQLite has no boolean.
    verbatim: Mapped[bool] = mapped_column(Boolean, default=True)


class Link(Base):
    """A call or reference from one chunk to another."""

    __tablename__ = "links"
    __table_args__ = (Index("links_run_src", "run_id", "src"), Index("links_run_dst", "run_id", "dst"))

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    src: Mapped[str] = mapped_column(String(64), primary_key=True)
    dst: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)


class Note(Base):
    """What a callee concluded, for its callers to read."""

    __tablename__ = "notes"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    note: Mapped[str] = mapped_column(Text)


class Finding(Base):
    """One claim about one chunk. JSONB for the same reason `Run.report` is."""

    __tablename__ = "findings"
    __table_args__ = (Index("findings_run_chunk", "run_id", "chunk_id"),)

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64))
    file: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Inspected(Base):
    """A chunk that has been looked at, so a re-run can tell "nothing found"
    from "not yet analysed"."""

    __tablename__ = "inspected"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class Span(Base):
    """One recorded step of a run: a model call, a tool call, a node."""

    __tablename__ = "spans"
    __table_args__ = (Index("spans_run_seq", "run_id", "seq"), Index("spans_run_parent", "run_id", "parent_id"))

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    parent_id: Mapped[str | None] = mapped_column(String(64))
    seq: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[float] = mapped_column(Float)
    ended_at: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(32))
    error: Mapped[str | None] = mapped_column(Text)

    #: Still text, still clipped. `trace/store.py`'s `clip` bounds these at
    #: 20,000 characters and replaces an over-long payload with a truncation
    #: marker; JSONB would accept the whole thing and quietly undo that.
    inputs: Mapped[str | None] = mapped_column(Text)
    outputs: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[int | None] = mapped_column(Integer)


class Vector_(Base):
    """A chunk's embedding, for the semantic fallback in `index/embed.py`.

    `pgvector` rather than the old BLOB: the fallback used to load every vector
    and score it in Python, which is a scan wearing an index's clothes.
    """

    __tablename__ = "vectors"

    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(128))
    embedding: Mapped[Any] = mapped_column(Vector(EMBED_DIMS))


class CachedResult(Base):
    """What a chunk was found to contain, keyed by content rather than by run.

    The one table with no `run_id`, and deliberately: the chunk id is derived
    from the code, so an unchanged unit in a new run hits what an older run
    concluded. That reuse is what "지난 검사에서 가져옴" is.
    """

    __tablename__ = "results"

    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recipe: Mapped[str] = mapped_column(String(64), primary_key=True)
    findings: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")
