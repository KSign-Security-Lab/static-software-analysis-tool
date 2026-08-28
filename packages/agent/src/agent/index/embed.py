"""Semantic search over the chunks already in the index.

The fallback path for the question the other tools answer badly: *is there a
check for this anywhere?* `search_text` is a regular expression, so asking it
that means guessing the identifier -- and `is_authorized` does not contain the
word "permission". Cosine over embedded chunks does not have to guess.

Deliberately narrow, and deliberately last. Similarity is not reachability: it
says two units look alike, never that tainted input flows from one to the other,
which is what `links` and `graph_path` answer exactly. Measured on three C
functions, "does anything check permissions before acting?" put `is_authorized`
0.14 clear of the field, and "shell command built from untrusted input" led by
0.04 -- right, but barely, because that second question is about reaching rather
than resembling. So this is a fourth way to look something up, not a replacement
for the context pack, which stays deterministic for the reasons in context.py.

`fastembed` is an optional extra (`agent[rag]`): it drags in onnxruntime and
downloads a model on first use, and an install that never asks a semantic
question should not pay for either. Everything here degrades to a clear message
rather than an import error.
"""

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

#: Small, fast and English. 384 dimensions, ~5s to first vector from cold.
#: Code is mostly English identifiers and comments, and a larger model buys
#: less here than the honest limits above cost.
MODEL_NAME = "BAAI/bge-small-en-v1.5"

def document_for(file: str, symbol: str, body: str) -> str:
    return f"{symbol} in {file}\n{body}"


class Unavailable(RuntimeError):
    """No `fastembed`, or no model. Said plainly rather than raised as ImportError."""


def _embedder():
    try:
        from fastembed import TextEmbedding
    except ImportError as err:  # pragma: no cover - depends on the extra
        raise Unavailable(
            "semantic search needs the optional 'rag' extra: uv sync --package agent --extra rag"
        ) from err
    return TextEmbedding(MODEL_NAME)


def build(store: ChunkStore, chunks: Iterable[tuple[str, str, str, str]] | None = None) -> int:
    """Embed every chunk that has no vector yet. Returns how many were added.

    Incremental by construction: re-indexing a tree where one file changed pays
    for that file, not for the tree. A chunk id is content-derived, so an edited
    function is a new id and an unedited one is already here.
    """
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
    """Nearest chunks to `query`: (score, file, symbol, start_line), best first.

    Builds the index on first use rather than at `build_index` time, so a run
    that never asks a semantic question never downloads a model.

    The ranking is the database's now. It used to load every vector, unpack it
    and score it in Python -- a scan wearing an index's clothes -- and pgvector's
    cosine operator does it in one statement with a `LIMIT` the planner can use.
    """
    build(store)

    model = _embedder()
    embedded = list(next(iter(model.embed([query]))))

    # `<=>` is cosine *distance*, so the score the callers expect is 1 - it.
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
