from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Sequence

from ..config import AgentConfig
from ..languages import spec_for_path
from .chunk import Chunk, chunk_source
from .links import Link, resolve_links
from .order import call_levels, inspection_order
from .reach import compute as compute_reach
from .store import ChunkStore

log = logging.getLogger(__name__)
__all__ = ["Chunk", "ChunkStore", "IndexResult", "Link", "build_index", "iter_source_files"]
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
        "__MACOSX",
    }
)

MAX_FILE_BYTES = 1_500_000


@dataclass(frozen=True)
class IndexResult:
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
    chunks: list[Chunk] = []
    indexed = 0
    skipped = 0
    for path in paths:
        text = files.get(path)
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
    links = resolve_links(chunks)
    store.add_chunks(chunks)
    store.add_links(links)
    store.set_order(inspection_order(chunks, links))
    store.set_levels(call_levels(chunks, links))
    store.set_reach(compute_reach(chunks, links, AgentConfig().entry_points))
    _write_knowledge_graph(store)
    return IndexResult(files_indexed=indexed, files_skipped=skipped, chunks=len(chunks), links=len(links))


def _write_knowledge_graph(store: ChunkStore) -> None:
    from ..knowledge import write_graph

    try:
        write_graph(store)
    except Exception:  # noqa: BLE001
        log.exception("could not write the knowledge graph for run %s", store.run_id)


def build_index(files: Mapping[str, str], store: ChunkStore) -> IndexResult:
    chunks, indexed, skipped = _chunk_tree(files, indexable(files))
    return _persist(store, chunks, indexed, skipped)


def index_paths(paths: Sequence[str], files: Mapping[str, str], store: ChunkStore) -> IndexResult:
    chunks, indexed, skipped = _chunk_tree(files, list(paths))
    return _persist(store, chunks, indexed, skipped)
