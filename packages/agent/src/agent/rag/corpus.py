from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from ..config import AgentConfig
from ..db import CorpusSample, ensure, session_factory
from ..ids import normalize_cwe
from ..index.chunk import FUNCTION_CHUNK_KIND, chunk_source
from ..index.embed import Unavailable, document_for

log = logging.getLogger(__name__)
MODEL_NAME = "jinaai/jina-embeddings-v2-base-code"
VULNERABLE = "vulnerable"
FIXED = "fixed"
_FIXED_WORDS = ("good", "patched", "safe", "fixed")
_VULNERABLE_WORDS = ("bad", "vuln", "unpatched", "unsafe")
_SOURCE_PREFIX = "// source:"
_BATCH = 256
_model = None


def _embedder():
    global _model
    if _model is None:
        try:
            from fastembed import TextEmbedding
        except ImportError as err:  # pragma: no cover - depends on the extra
            raise Unavailable(
                "the corpus needs the optional 'rag' extra: uv sync --extra rag"
            ) from err
        _model = TextEmbedding(MODEL_NAME)
    return _model


@dataclass(frozen=True)
class Sample:
    sample_id: str
    cwe: str
    variant: str
    file: str
    symbol: str
    language: str
    body: str
    source: str


def variant_of(name: str) -> str:
    lowered = name.lower()
    if any(word in lowered for word in _FIXED_WORDS):
        return FIXED
    if any(word in lowered for word in _VULNERABLE_WORDS):
        return VULNERABLE
    return VULNERABLE


def cwe_of(path: Path, root: Path) -> str | None:
    for parent in path.parents:
        if parent == root.parent:
            break
        found = normalize_cwe(parent.name)
        if found:
            return found
        if parent == root:
            break
    return None


def source_of(text: str) -> str:
    first = text.lstrip().split("\n", 1)[0].strip()
    if first.startswith(_SOURCE_PREFIX):
        return first[len(_SOURCE_PREFIX) :].strip()
    return ""


def read(root: Path) -> tuple[list[Sample], int]:
    samples: list[Sample] = []
    skipped = 0
    for path in sorted(_files(root)):
        cwe = cwe_of(path, root)
        if cwe is None:
            skipped += 1
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            skipped += 1
            continue

        relative = path.relative_to(root).as_posix()
        variant = variant_of(path.name)
        source = source_of(text)
        chunks = [c for c in chunk_source(relative, text) if c.kind == FUNCTION_CHUNK_KIND]
        if not chunks:
            skipped += 1
            continue
        for chunk in chunks:
            samples.append(
                Sample(
                    sample_id=chunk.chunk_id,
                    cwe=cwe,
                    variant=variant,
                    file=relative,
                    symbol=chunk.symbol,
                    language=chunk.language,
                    body=chunk.body,
                    source=source,
                )
            )
    return samples, skipped


def _files(root: Path) -> Iterator[Path]:
    if not root.is_dir():
        return
    for path in root.rglob("*"):
        if path.is_file() and not path.name.startswith("."):
            yield path


def ingest(root: Path | None = None, config: AgentConfig | None = None) -> dict[str, int]:
    config = config or AgentConfig()
    root = Path(root) if root is not None else config.corpus_dir

    ensure()

    samples, skipped = read(root)
    stored = _stored_ids()
    fresh = [s for s in samples if s.sample_id not in stored]
    on_disk = {s.sample_id for s in samples}
    removed = _forget(stored - on_disk) if samples else 0

    if not fresh:
        return {"embedded": 0, "total": len(samples), "skipped": skipped, "removed": removed}

    added = _embed_and_store(fresh)
    log.info("corpus: embedded %d new sample(s) of %d under %s", added, len(samples), root)
    return {"embedded": added, "total": len(samples), "skipped": skipped, "removed": removed}


def _stored_ids() -> set[str]:
    with session_factory()() as session:
        return set(
            session.scalars(select(CorpusSample.sample_id).where(CorpusSample.model == MODEL_NAME))
        )


def _forget(gone: Iterable[str]) -> int:
    ids = list(gone)
    if not ids:
        return 0
    with session_factory()() as session:
        session.execute(delete(CorpusSample).where(CorpusSample.sample_id.in_(ids)))
        session.commit()
    return len(ids)


def _embed_and_store(samples: list[Sample]) -> int:
    model = _embedder()
    written = 0
    for start in range(0, len(samples), _BATCH):
        batch = samples[start : start + _BATCH]
        vectors = list(model.embed([document_for(s.file, s.symbol, s.body) for s in batch]))
        with session_factory()() as session:
            statement = insert(CorpusSample)
            session.execute(
                statement.on_conflict_do_update(
                    index_elements=["sample_id"],
                    set_={
                        "cwe": statement.excluded.cwe,
                        "variant": statement.excluded.variant,
                        "source": statement.excluded.source,
                        "model": statement.excluded.model,
                        "embedding": statement.excluded.embedding,
                    },
                ),
                [
                    {
                        "sample_id": s.sample_id,
                        "cwe": s.cwe,
                        "variant": s.variant,
                        "file": s.file,
                        "symbol": s.symbol,
                        "language": s.language,
                        "body": s.body,
                        "source": s.source,
                        "model": MODEL_NAME,
                        "embedding": list(vector),
                    }
                    for s, vector in zip(batch, vectors)
                ],
            )
            session.commit()
        written += len(batch)
    return written


def search(query: str, cwe: str = "", limit: int = 5) -> list[tuple[float, CorpusSample]]:
    model = _embedder()
    embedded = list(next(iter(model.embed([query]))))
    distance = CorpusSample.embedding.cosine_distance(embedded)
    conditions = [CorpusSample.model == MODEL_NAME]
    if cwe:
        normalized = normalize_cwe(cwe)
        if normalized:
            conditions.append(CorpusSample.cwe == normalized)

    with session_factory()() as session:
        rows = session.execute(
            select(distance, CorpusSample).where(*conditions).order_by(distance).limit(limit)
        ).all()
    return [(1.0 - float(d), sample) for d, sample in rows]


def counts() -> list[tuple[str, str, int]]:
    from sqlalchemy import func

    with session_factory()() as session:
        return [
            (cwe, variant, int(n))
            for cwe, variant, n in session.execute(
                select(CorpusSample.cwe, CorpusSample.variant, func.count())
                .group_by(CorpusSample.cwe, CorpusSample.variant)
                .order_by(CorpusSample.cwe, CorpusSample.variant)
            ).all()
        ]


__all__ = ["FIXED", "VULNERABLE", "Sample", "Unavailable", "counts", "cwe_of", "ingest", "read", "search", "variant_of"]
