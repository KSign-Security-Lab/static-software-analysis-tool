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

EMBED_DIMS = 384
CORPUS_EMBED_DIMS = 768


class Base(DeclarativeBase):
    pass


def _now() -> float:
    return time.time()


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    owner: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[float] = mapped_column(Float, default=_now)
    updated_at: Mapped[float] = mapped_column(Float, default=_now, onupdate=_now)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    meta: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    knowledge: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    files: Mapped[list[File]] = relationship(back_populates="run", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"
    __table_args__ = (UniqueConstraint("run_id", "path", name="files_run_path"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text)
    size: Mapped[int] = mapped_column(Integer)
    sha: Mapped[str] = mapped_column(String(64))
    run: Mapped[Run] = relationship(back_populates="files")


class Chunk(Base):
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
    defines: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    refs: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    types_used: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    includes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    verbatim: Mapped[bool] = mapped_column(Boolean, default=True)


class Link(Base):
    __tablename__ = "links"
    __table_args__ = (Index("links_run_src", "run_id", "src"), Index("links_run_dst", "run_id", "dst"))
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    src: Mapped[str] = mapped_column(String(64), primary_key=True)
    dst: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), primary_key=True)
    symbol: Mapped[str] = mapped_column(Text, primary_key=True)


class Note(Base):
    __tablename__ = "notes"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    note: Mapped[str] = mapped_column(Text)


class Finding(Base):
    __tablename__ = "findings"
    __table_args__ = (Index("findings_run_chunk", "run_id", "chunk_id"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64))
    file: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)


class Inspected(Base):
    __tablename__ = "inspected"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)


class Span(Base):
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
    inputs: Mapped[str | None] = mapped_column(Text)
    outputs: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[str | None] = mapped_column(Text)
    tokens: Mapped[int | None] = mapped_column(Integer)


class Vector_(Base):
    __tablename__ = "vectors"
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(128))
    embedding: Mapped[Any] = mapped_column(Vector(EMBED_DIMS))


class CachedResult(Base):
    __tablename__ = "results"
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    recipe: Mapped[str] = mapped_column(String(64), primary_key=True)
    findings: Mapped[str] = mapped_column(Text)
    note: Mapped[str] = mapped_column(Text, default="")


class HarnessConfig(Base):
    __tablename__ = "harness_configs"
    config_hash: Mapped[str] = mapped_column(String(32), primary_key=True)
    knobs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    label: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[float] = mapped_column(Float, default=_now)


class ConfigProposal(Base):
    __tablename__ = "config_proposals"
    __table_args__ = (Index("config_proposals_base", "base_hash"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    base_hash: Mapped[str] = mapped_column(String(32))
    proposed_hash: Mapped[str] = mapped_column(String(32))
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    metric: Mapped[str] = mapped_column(String(64), default="")
    direction: Mapped[str] = mapped_column(String(8), default="up")
    status: Mapped[str] = mapped_column(String(16), default="proposed")
    replay: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[float] = mapped_column(Float, default=_now)


class PlanItem(Base):
    __tablename__ = "plan_items"
    __table_args__ = (Index("plan_items_run_order", "run_id", "order_key"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    chunk_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    reason: Mapped[str] = mapped_column(Text, default="")
    order_key: Mapped[int] = mapped_column(Integer)
    priority: Mapped[int] = mapped_column(Integer, default=0)


class PlanEventRow(Base):
    __tablename__ = "plan_events"
    __table_args__ = (Index("plan_events_run_seq", "run_id", "seq"),)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(24))
    target: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str] = mapped_column(Text, default="")
    span_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[float] = mapped_column(Float, default=_now)


class CorpusSample(Base):
    __tablename__ = "corpus"
    sample_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    cwe: Mapped[str] = mapped_column(String(16))
    variant: Mapped[str] = mapped_column(String(16))
    file: Mapped[str] = mapped_column(Text)
    symbol: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(32))
    body: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(128))
    embedding: Mapped[Any] = mapped_column(Vector(CORPUS_EMBED_DIMS))
    __table_args__ = (
        Index("corpus_cwe", "cwe"),
        Index(
            "corpus_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )
