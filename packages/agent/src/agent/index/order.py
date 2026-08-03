"""Chunk inspection order: callees before callers.

This is the decision the whole cross-chunk design rests on. Analysing
``download_firmware`` before ``handle_update_firmware`` means that by the time
the caller is inspected, the callee's note -- "builds a shell command from its
argument with no validation" -- is already in the store and can be injected into
the caller's context. Taint crosses chunk boundaries without ever putting the
whole tree in one prompt.

Reverse the order and the caller is analysed blind, which is the ordinary
failure of chunk-at-a-time analysis.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Sequence

from .chunk import FILE_CHUNK_KIND, Chunk
from .links import CALLS, Link


def inspection_order(chunks: Sequence[Chunk], links: Sequence[Link]) -> list[str]:
    """Chunk ids in the order they should be inspected.

    File chunks come first -- they carry the struct layouts and globals that the
    functions are about to be judged against, and they call nothing.

    Function chunks follow in depth-first postorder over the call graph, which
    emits every callee before its caller. Recursion and mutual recursion are
    cycles with no valid topological order; the walk breaks them by visiting the
    lowest chunk id first and treating the back edge as already-visited, so the
    cycle's members still each appear exactly once.
    """
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
    #: Nodes on the current DFS path. A neighbour that is on the path is a back
    #: edge -- a cycle -- and is skipped rather than recursed into.
    on_path: set[str] = set()

    def visit(start: str) -> None:
        # Iterative, because a deep call chain in a large upload would otherwise
        # blow the recursion limit.
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
