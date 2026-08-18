"""Known weaknesses on disk, embedded so a claim can be checked against them.

The verifier had nothing outside the file it was reading. `cwe` is a free string
the model emits -- `ids.normalize_cwe` checks it looks like one and nothing ever
looked it up -- so "is this really CWE-121" was a question the tool could only
put back to the same model that had just answered it. Two runs over the same
three files produced CWE-787 and CWE-122 for near-identical overflows.

This is the one retrieval case with no key. Every other question the agent asks
is exact -- `find_definition`, `find_callers` -- and answered from the index in
milliseconds. "What is this code *like*" has nothing to look up by, which is
what similarity is for and the only thing it is better at than a lookup.

Layout carries the labels, so adding a sample is dropping a file in a folder:

    corpus/CWE-121_stack_based_buffer_overflow/strcpy_unbounded_bad.c
                 └─ the CWE                    └─ the variant

Vulnerable and fixed are stored as separate samples under the same CWE. Which
one a piece of code resembles *more* is the useful question, and the fixed half
is what lets retrieval argue against a finding rather than only for it.
"""

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

#: Code-trained, and not the model `index/embed.py` uses.
#:
#: Measured, on the ten held-out functions in `tests/test_corpus.py`: asked to
#: name the weakness, `BAAI/bge-small-en-v1.5` got 4 of 10 and this got 8. The
#: English model was scoring shared vocabulary rather than shared meaning -- a
#: `system()` command injection and a heap overflow that both happen to call
#: `snprintf` came back as each other's nearest neighbours.
#:
#: The run index keeps the smaller model on purpose. It answers "where in this
#: code", where the query is already a name and similarity is a fallback; this
#: answers "what is this code like", which is the whole job.
MODEL_NAME = "jinaai/jina-embeddings-v2-base-code"

VULNERABLE = "vulnerable"
FIXED = "fixed"

#: The same vocabulary `gnn/dataset/JsonDataset.py::_infer_label_from_json` uses
#: on Juliet filenames. Kept identical rather than invented again: a corpus
#: labelled one way here and another way there is two corpora.
_FIXED_WORDS = ("good", "patched", "safe", "fixed")
_VULNERABLE_WORDS = ("bad", "vuln", "unpatched", "unsafe")

#: Provenance, written by the CVE scrape and optional everywhere else.
_SOURCE_PREFIX = "// source:"

#: Embedding a few thousand samples in one call holds every vector in memory at
#: once for no gain; the model is happiest fed steadily.
_BATCH = 256

_model = None


def _embedder():
    """The code model, loaded once. ~0.6GB on first use, then cached by HF."""
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
    """One function from the corpus, labelled, before it has been embedded."""

    sample_id: str
    cwe: str
    variant: str
    file: str
    symbol: str
    language: str
    body: str
    source: str


def variant_of(name: str) -> str:
    """`vulnerable` or `fixed`, from the filename.

    Unlabelled means vulnerable. A file sitting in a CWE folder saying nothing
    about itself is presumed to demonstrate that CWE, which is the safer way to
    be wrong: a fixed sample mislabelled vulnerable weakens a match, while a
    vulnerable one mislabelled fixed argues *against* a real finding.
    """
    lowered = name.lower()
    if any(word in lowered for word in _FIXED_WORDS):
        return FIXED
    if any(word in lowered for word in _VULNERABLE_WORDS):
        return VULNERABLE
    return VULNERABLE


def cwe_of(path: Path, root: Path) -> str | None:
    """The CWE from the nearest labelled ancestor directory, or None.

    Nearest rather than outermost so a tree can be grouped however suits it --
    `CWE-121_stack/glibc/...` keeps the CWE while `scraped/CWE-416_uaf/...`
    picks one up from further in.
    """
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
    """The `// source:` line, if the file opens with one."""
    first = text.lstrip().split("\n", 1)[0].strip()
    if first.startswith(_SOURCE_PREFIX):
        return first[len(_SOURCE_PREFIX) :].strip()
    return ""


def read(root: Path) -> tuple[list[Sample], int]:
    """Every labelled function under `root`. Returns them and how many files were skipped.

    Skipped rather than raised: a corpus is a directory people put things in,
    and one file in an unlabelled folder must not stop the other four hundred
    from being ingested. The count is returned so the caller can say so.
    """
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

        # Function chunks only. A file chunk is the includes and whatever sits
        # between definitions -- boilerplate, near-identical across samples, and
        # it would match every query about anything.
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
    """Embed everything under `root` that is not already stored.

    Idempotent by construction: `sample_id` is `chunk_id_for(file, symbol, body)`
    and whitespace-normalised, so re-ingesting unchanged code computes the same
    ids and finds them all present.

    That matters more than it sounds. This runs from `scripts/up.sh` on every
    dev start, and constructing the embedder costs about five seconds cold -- so
    the check for "is there anything to do" happens *before* the model is
    touched, and a corpus that has not changed costs one query.
    """
    config = config or AgentConfig()
    root = Path(root) if root is not None else config.corpus_dir

    # Nothing else creates this table outside the test fixtures. See
    # `db/schema.ensure`.
    ensure()

    samples, skipped = read(root)
    stored = _stored_ids()
    fresh = [s for s in samples if s.sample_id not in stored]

    # Gone from disk. A corpus is edited, and a sample deleted from the tree
    # that stayed in the index would keep being retrieved as evidence.
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
        # `document_for` is what `index/embed.py` embeds a chunk as. The same
        # shape on both sides is what makes a run's code and a corpus sample
        # comparable at all.
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
    """Nearest samples to `query`, best first.

    Not scoped to a run, and that is the point: every other store in this
    package is keyed by `run_id` because it describes one inspection. These
    describe weaknesses, and were recorded before the run existed.
    """
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
    # `<=>` is cosine *distance*; callers want a score that rises with likeness.
    return [(1.0 - float(d), sample) for d, sample in rows]


def counts() -> list[tuple[str, str, int]]:
    """(cwe, variant, n), for `agent corpus stats`."""
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
