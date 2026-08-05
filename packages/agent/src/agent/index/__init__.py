"""Source tree -> chunk store.

The whole indexing stage is deterministic and LLM-free: walk the tree, chunk
each supported file, resolve references into links, compute the inspection
order, write it all to SQLite. Everything downstream reads the store.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Sequence

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


def iter_source_files(root: Path) -> Iterator[Path]:
    """Every indexable file under ``root``, deterministically ordered."""
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        if spec_for_path(path.name) is None:
            continue
        yield path


def relative_posix(path: Path, root: Path) -> str:
    """Run-relative POSIX path -- the only path form that crosses the wire."""
    return str(PurePosixPath(*path.relative_to(root).parts))


def _chunk_tree(root: Path, paths: Sequence[Path]) -> tuple[list[Chunk], int, int]:
    """Chunk each path, counting what could not be read or parsed."""
    chunks: list[Chunk] = []
    indexed = 0
    skipped = 0
    for path in paths:
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                skipped += 1
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            skipped += 1
            continue

        file_chunks = chunk_source(relative_posix(path, root), text)
        if file_chunks:
            chunks.extend(file_chunks)
            indexed += 1
        else:
            skipped += 1
    return chunks, indexed, skipped


def _persist(store: ChunkStore, root: Path, chunks: Sequence[Chunk], indexed: int, skipped: int) -> IndexResult:
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
    _write_knowledge_graph(store, root)
    return IndexResult(files_indexed=indexed, files_skipped=skipped, chunks=len(chunks), links=len(links))


def _write_knowledge_graph(store: ChunkStore, root: Path) -> None:
    """The tree as a graph, beside the index that produced it.

    Here rather than at each of the five places that index, because it is
    derived from exactly this data and invalidated by exactly these events, and
    a derived file somebody has to remember to refresh is a stale file.

    Imported inside the function: `agent.knowledge` reads a ChunkStore, so at
    module scope the two would import each other. Failure is logged and
    swallowed -- a missing map costs the graph tools, and is not a reason to
    refuse to index a tree.
    """
    from ..knowledge import GRAPH_FILE, write_graph

    try:
        write_graph(store, root, store.path.parent / GRAPH_FILE)
    except Exception:  # noqa: BLE001
        log.exception("could not write the knowledge graph beside %s", store.path)


def build_index(root: Path, store: ChunkStore) -> IndexResult:
    """Index a whole source tree into ``store``."""
    chunks, indexed, skipped = _chunk_tree(root, list(iter_source_files(root)))
    return _persist(store, root, chunks, indexed, skipped)


def index_paths(paths: Sequence[Path], root: Path, store: ChunkStore) -> IndexResult:
    """Index an explicit file list rather than a whole tree."""
    chunks, indexed, skipped = _chunk_tree(root, paths)
    return _persist(store, root, chunks, indexed, skipped)
