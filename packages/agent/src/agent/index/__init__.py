"""Source tree -> chunk store.

The whole indexing stage is deterministic and LLM-free: walk the tree, chunk
each supported file, resolve references into links, compute the inspection
order, write it all to SQLite. Everything downstream reads the store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Sequence

from ..languages import spec_for_path
from .chunk import Chunk, chunk_source
from .links import Link, resolve_links
from .order import call_levels, inspection_order
from .store import ChunkStore

log = logging.getLogger(__name__)

__all__ = ["Chunk", "ChunkStore", "IndexResult", "Link", "build_index", "iter_source_files"]

#: Directories that never contain source worth inspecting. Walking them wastes
#: minutes on a real upload and floods the link graph with vendored symbols.
SKIP_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        "target",
        ".next",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "vendor",
        "third_party",
    }
)

#: Files above this are generated, minified or amalgamated (sqlite3.c is 8 MB).
#: Chunking them produces units no model can reason about.
MAX_FILE_BYTES = 1_500_000


@dataclass(frozen=True)
class IndexResult:
    """What indexing produced, for reporting back to the caller."""

    files_indexed: int
    files_skipped: int
    chunks: int
    links: int

    def as_dict(self) -> dict[str, int]:
        return {
            "files_indexed": self.files_indexed,
            "files_skipped": self.files_skipped,
            "chunks": self.chunks,
            "links": self.links,
        }


def indexable(paths: Iterable[str]) -> list[str]:
    """The paths worth parsing, deterministically ordered.

    Was a walk of the tree. The tree is a `dict[path, text]` now, so this
    filters names instead of stat-ing files -- same two rules: nothing under a
    skipped directory, nothing whose extension has no grammar.
    """
    out = []
    for path in sorted(paths):
        parts = PurePosixPath(path).parts
        if any(part in SKIP_DIRS for part in parts[:-1]):
            continue
        if spec_for_path(parts[-1]) is None:
            continue
        out.append(path)
    return out


def _chunk_tree(files: Mapping[str, str], paths: Sequence[str]) -> tuple[list[Chunk], int, int]:
    """Chunk each path, counting what could not be read or parsed."""
    chunks: list[Chunk] = []
    indexed = 0
    skipped = 0
    for path in paths:
        text = files.get(path)
        # The size cap is on the text now rather than on a stat: the row is
        # already in memory, so the cap is about what is worth parsing.
        if text is None or len(text.encode("utf-8", errors="ignore")) > MAX_FILE_BYTES:
            skipped += 1
            continue

        file_chunks = chunk_source(path, text)
        if file_chunks:
            chunks.extend(file_chunks)
            indexed += 1
        else:
            skipped += 1
    return chunks, indexed, skipped


def _persist(store: ChunkStore, chunks: Sequence[Chunk], indexed: int, skipped: int) -> IndexResult:
    """Resolve links over the full chunk set, order it, and write it down.

    Link resolution is global on purpose: a reference in one file resolves
    against definitions in every other, so it cannot be done per file.
    """
    links = resolve_links(chunks)
    store.add_chunks(chunks)
    store.add_links(links)
    store.set_order(inspection_order(chunks, links))
    # Written here rather than worked out per run: it is a property of the tree,
    # and it is what tells the inspection which chunks may go at once.
    store.set_levels(call_levels(chunks, links))
    _write_knowledge_graph(store)
    return IndexResult(files_indexed=indexed, files_skipped=skipped, chunks=len(chunks), links=len(links))


def _write_knowledge_graph(store: ChunkStore) -> None:
    """The tree as a graph, on the run that produced it.

    Here rather than at each of the five places that index, because it is
    derived from exactly this data and invalidated by exactly these events, and
    a derived artifact somebody has to remember to refresh is a stale one.

    Imported inside the function: `agent.knowledge` reads a ChunkStore, so at
    module scope the two would import each other. Failure is logged and
    swallowed -- a missing map costs the graph tools, and is not a reason to
    refuse to index a tree.
    """
    from ..knowledge import write_graph

    try:
        write_graph(store)
    except Exception:  # noqa: BLE001
        log.exception("could not write the knowledge graph for run %s", store.run_id)


def build_index(files: Mapping[str, str], store: ChunkStore) -> IndexResult:
    """Index a whole source tree into ``store``.

    Takes the tree as `{path: text}` rather than a root directory: a run's files
    are rows, and handing the indexer a mapping is what stops it needing a
    filesystem to walk.
    """
    chunks, indexed, skipped = _chunk_tree(files, indexable(files))
    return _persist(store, chunks, indexed, skipped)


def index_paths(paths: Sequence[str], files: Mapping[str, str], store: ChunkStore) -> IndexResult:
    """Index an explicit file list rather than a whole tree."""
    chunks, indexed, skipped = _chunk_tree(files, list(paths))
    return _persist(store, chunks, indexed, skipped)
