"""Chunk inspection order: callees before callers.

The decision the cross-chunk design rests on. By the time a caller is inspected
its callee's note is in the store and can be injected. Reverse it and the caller
is analysed blind, which is the ordinary failure of chunk-at-a-time analysis.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from .chunk import FILE_CHUNK_KIND, Chunk
from .links import CALLS, Link


def inspection_order(chunks: Sequence[Chunk], links: Sequence[Link]) -> list[str]:
    """File chunks first -- they carry the layouts the functions are judged
    against and call nothing. Then DFS postorder over the call graph, which
    emits every callee before its caller. Cycles have no valid order; the walk
    breaks them so each member still appears exactly once."""
    by_id = {chunk.chunk_id: chunk for chunk in chunks}
    edges: dict[str, list[str]] = defaultdict(list)
    for link in links:
        if link.kind == CALLS and link.src in by_id and link.dst in by_id:
            edges[link.src].append(link.dst)
    for targets in edges.values():
        targets.sort()

    def sort_key(chunk: Chunk) -> tuple[str, int, str]:
        return (chunk.file, chunk.start_line, chunk.chunk_id)

    files = sorted((c for c in chunks if c.kind == FILE_CHUNK_KIND), key=sort_key)
    functions = sorted((c for c in chunks if c.kind != FILE_CHUNK_KIND), key=sort_key)

    order: list[str] = [chunk.chunk_id for chunk in files]
    emitted = set(order)
    # A neighbour already on the path is a back edge, so it is skipped.
    on_path: set[str] = set()

    def visit(start: str) -> None:
        # Iterative: a deep call chain would blow the recursion limit.
        stack: list[tuple[str, bool]] = [(start, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                on_path.discard(node)
                if node not in emitted:
                    emitted.add(node)
                    order.append(node)
                continue
            if node in emitted or node in on_path:
                continue
            on_path.add(node)
            stack.append((node, True))
            for neighbour in reversed(edges.get(node, [])):
                if neighbour not in emitted and neighbour not in on_path:
                    stack.append((neighbour, False))

    for chunk in functions:
        visit(chunk.chunk_id)

    return order
