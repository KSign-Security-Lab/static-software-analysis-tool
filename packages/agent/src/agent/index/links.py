"""Resolve chunk references into edges.

Symbol-table work, not search: a ``references`` entry matching another chunk's
``defines`` *is* a call edge. What it cannot resolve -- function pointers,
macro-generated calls -- it leaves alone rather than guessing.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Iterable, Sequence

from .chunk import FILE_CHUNK_KIND, Chunk

CALLS = "calls"
USES_TYPE = "uses_type"
FILE_DEPENDS = "file_depends"

# Beyond this the name is an overload or a per-TU stub; linking to all of them
# buries the real edge.
MAX_AMBIGUITY = 4


@dataclass(frozen=True)
class Link:
    """A resolved edge between two chunks."""

    src: str
    dst: str
    kind: str
    symbol: str


def _by_defined_symbol(chunks: Sequence[Chunk]) -> dict[str, list[Chunk]]:
    index: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        for symbol in chunk.defines:
            index[symbol].append(chunk)
    return index


def _pick(candidates: Sequence[Chunk], source: Chunk) -> list[Chunk]:
    """Same-file wins: a static helper shadows an identically named function
    elsewhere, which is the common case in C."""
    same_file = [c for c in candidates if c.file == source.file and c.chunk_id != source.chunk_id]
    if same_file:
        return same_file[:1]
    others = [c for c in candidates if c.chunk_id != source.chunk_id]
    if not others or len(others) > MAX_AMBIGUITY:
        return []
    return others


def _include_target(include: str) -> str | None:
    """Only local includes; system headers are not in the tree."""
    if '"' in include:
        parts = include.split('"')
        if len(parts) >= 2 and parts[1]:
            return parts[1]
    return None


def _resolve_include(target: str, source_file: str, by_file: dict[str, list[Chunk]]) -> Chunk | None:
    """Match an include target against indexed files, nearest first."""
    candidate = str(PurePosixPath(source_file).parent / target)
    normalized = str(PurePosixPath(candidate)) if candidate != target else target
    for key in (normalized, target):
        chunks = by_file.get(key)
        if chunks:
            return chunks[0]
    suffix = "/" + PurePosixPath(target).name
    matches = [chunks[0] for path, chunks in by_file.items() if path.endswith(suffix) or path == target]
    return matches[0] if len(matches) == 1 else None


def resolve_links(chunks: Sequence[Chunk]) -> list[Link]:
    """Every resolvable edge among these chunks, deterministically ordered."""
    defined = _by_defined_symbol(chunks)
    file_chunks: dict[str, list[Chunk]] = defaultdict(list)
    for chunk in chunks:
        if chunk.kind == FILE_CHUNK_KIND:
            file_chunks[chunk.file].append(chunk)

    links: list[Link] = []
    seen: set[tuple[str, str, str, str]] = set()

    def add(src: str, dst: str, kind: str, symbol: str) -> None:
        key = (src, dst, kind, symbol)
        if src != dst and key not in seen:
            seen.add(key)
            links.append(Link(src=src, dst=dst, kind=kind, symbol=symbol))

    for chunk in chunks:
        for symbol in chunk.references:
            for target in _pick(defined.get(symbol, []), chunk):
                add(chunk.chunk_id, target.chunk_id, CALLS, symbol)
        for symbol in chunk.types_used:
            for target in _pick(defined.get(symbol, []), chunk):
                add(chunk.chunk_id, target.chunk_id, USES_TYPE, symbol)
        for include in chunk.includes:
            target_path = _include_target(include)
            if target_path is None:
                continue
            target_chunk = _resolve_include(target_path, chunk.file, file_chunks)
            if target_chunk is not None:
                add(chunk.chunk_id, target_chunk.chunk_id, FILE_DEPENDS, target_path)

    links.sort(key=lambda link: (link.src, link.kind, link.symbol, link.dst))
    return links


def callees(links: Iterable[Link], chunk_id: str) -> list[str]:
    """Chunks this one calls."""
    return [link.dst for link in links if link.src == chunk_id and link.kind == CALLS]


def callers(links: Iterable[Link], chunk_id: str) -> list[str]:
    """Chunks that call this one."""
    return [link.src for link in links if link.dst == chunk_id and link.kind == CALLS]
