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
import sqlite3
import struct
from typing import Iterable, Sequence

from .store import ChunkStore

log = logging.getLogger(__name__)

#: Small, fast and English. 384 dimensions, ~5s to first vector from cold.
#: Code is mostly English identifiers and comments, and a larger model buys
#: less here than the honest limits above cost.
MODEL_NAME = "BAAI/bge-small-en-v1.5"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vectors (
    chunk_id TEXT PRIMARY KEY,
    model    TEXT NOT NULL,
    vec      BLOB NOT NULL
);
"""

#: What a chunk is embedded as. The symbol and file earn their place: a bare
#: body embeds the same whether it is called `is_authorized` or `f`, and the
#: name is often the strongest signal of intent in the whole unit.
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


def _pack(vector: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vector)}f", *vector)


def _unpack(blob: bytes) -> list[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: Sequence[float]) -> float:
    return _dot(a, a) ** 0.5


def build(store: ChunkStore, chunks: Iterable[tuple[str, str, str, str]] | None = None) -> int:
    """Embed every chunk that has no vector yet. Returns how many were added.

    Incremental by construction: re-indexing a tree where one file changed pays
    for that file, not for the tree. A chunk id is content-derived, so an edited
    function is a new id and an unedited one is already here.
    """
    store.conn.executescript(SCHEMA)
    rows = list(chunks) if chunks is not None else store.conn.execute(
        "SELECT chunk_id, file, symbol, body FROM chunks WHERE chunk_id NOT IN "
        "(SELECT chunk_id FROM vectors WHERE model = ?)",
        (MODEL_NAME,),
    ).fetchall()
    if not rows:
        return 0

    model = _embedder()
    documents = [document_for(file, symbol, body) for _, file, symbol, body in rows]
    vectors = model.embed(documents)
    store.conn.executemany(
        "INSERT OR REPLACE INTO vectors (chunk_id, model, vec) VALUES (?, ?, ?)",
        [(row[0], MODEL_NAME, _pack(list(vec))) for row, vec in zip(rows, vectors)],
    )
    store.conn.commit()
    return len(rows)


def search(store: ChunkStore, query: str, limit: int = 5) -> list[tuple[float, str, str, int]]:
    """Nearest chunks to `query`: (score, file, symbol, start_line), best first.

    Builds the index on first use rather than at `build_index` time, so a run
    that never asks a semantic question never downloads a model.
    """
    build(store)

    try:
        rows = store.conn.execute(
            "SELECT v.chunk_id, v.vec, c.file, c.symbol, c.start_line "
            "FROM vectors v JOIN chunks c ON c.chunk_id = v.chunk_id WHERE v.model = ?",
            (MODEL_NAME,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    if not rows:
        return []

    model = _embedder()
    q = list(next(iter(model.embed([query]))))
    qn = _norm(q) or 1.0

    scored = []
    for _chunk_id, blob, file, symbol, start_line in rows:
        vec = _unpack(blob)
        denominator = (_norm(vec) or 1.0) * qn
        scored.append((_dot(vec, q) / denominator, file, symbol, start_line))
    scored.sort(key=lambda row: row[0], reverse=True)
    return scored[:limit]
