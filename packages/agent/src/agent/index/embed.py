from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from ..db import Chunk as ChunkRow
from ..db import Vector_ as VectorRow
from ..db import session_factory
from .store import ChunkStore

log = logging.getLogger(__name__)
MODEL_NAME = "BAAI/bge-small-en-v1.5"

def document_for(file: str, symbol: str, body: str) -> str:
    return f"{symbol} in {file}\n{body}"


class Unavailable(RuntimeError):
    pass


def _embedder():
    try:
        from fastembed import TextEmbedding
    except ImportError as err:  # pragma: no cover - depends on the extra
        raise Unavailable(
            "semantic search needs the optional 'rag' extra: uv sync --package agent --extra rag"
        ) from err
    return TextEmbedding(MODEL_NAME)


def build(store: ChunkStore, chunks: Iterable[tuple[str, str, str, str]] | None = None) -> int:
    sessions = session_factory()
    if chunks is not None:
        rows = list(chunks)
    else:
        with sessions() as session:
            embedded = select(VectorRow.chunk_id).where(
                VectorRow.run_id == store.run_id, VectorRow.model == MODEL_NAME
            )
            rows = list(
                session.execute(
                    select(ChunkRow.chunk_id, ChunkRow.file, ChunkRow.symbol, ChunkRow.body).where(
                        ChunkRow.run_id == store.run_id, ChunkRow.chunk_id.not_in(embedded)
                    )
                ).all()
            )
    if not rows:
        return 0

    model = _embedder()
    documents = [document_for(file, symbol, body) for _, file, symbol, body in rows]
    vectors = model.embed(documents)

    with sessions() as session:
        statement = insert(VectorRow)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=["run_id", "chunk_id"],
                set_={"model": statement.excluded.model, "embedding": statement.excluded.embedding},
            ),
            [
                {
                    "run_id": store.run_id,
                    "chunk_id": row[0],
                    "model": MODEL_NAME,
                    "embedding": list(vec),
                }
                for row, vec in zip(rows, vectors)
            ],
        )
        session.commit()
    return len(rows)


def search(store: ChunkStore, query: str, limit: int = 5) -> list[tuple[float, str, str, int]]:
    build(store)

    model = _embedder()
    embedded = list(next(iter(model.embed([query]))))
    distance = VectorRow.embedding.cosine_distance(embedded)
    with session_factory()() as session:
        rows = session.execute(
            select(distance, ChunkRow.file, ChunkRow.symbol, ChunkRow.start_line)
            .join(
                ChunkRow,
                (ChunkRow.run_id == VectorRow.run_id) & (ChunkRow.chunk_id == VectorRow.chunk_id),
            )
            .where(VectorRow.run_id == store.run_id, VectorRow.model == MODEL_NAME)
            .order_by(distance)
            .limit(limit)
        ).all()

    return [(1.0 - float(d), file, symbol, start_line) for d, file, symbol, start_line in rows]
