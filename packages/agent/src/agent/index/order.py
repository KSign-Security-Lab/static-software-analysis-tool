"""Chunk inspection order: callees before callers.

The decision the cross-chunk design rests on. By the time a caller is inspected
its callee's note is in the store and can be injected. Reverse it and the caller
is analysed blind, which is the ordinary failure of chunk-at-a-time analysis.

:func:`call_levels` answers the follow-up question -- which chunks may be
inspected *at the same time*. Two chunks at the same depth cannot call each
other, so running them together costs nothing that the ordering was protecting.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

from .chunk import FILE_CHUNK_KIND, Chunk
from .links import CALLS, Link


def _sort_key(chunk: Chunk) -> tuple[str, int, str]:
    return (chunk.file, chunk.start_line, chunk.chunk_id)


def _call_graph(chunks: Sequence[Chunk], links: Sequence[Link]) -> dict[str, list[str]]:
    """Callee lists, sorted, over links whose ends are both in this index.

    Shared by the ordering and the levelling so the two cannot disagree about
    what calls what -- and so a cycle is the same cycle to both of them.
    """
    known = {chunk.chunk_id for chunk in chunks}
    edges: dict[str, list[str]] = defaultdict(list)
    for link in links:
        if link.kind == CALLS and link.src in known and link.dst in known:
            edges[link.src].append(link.dst)
    for targets in edges.values():
        targets.sort()
    return edges


def inspection_order(chunks: Sequence[Chunk], links: Sequence[Link]) -> list[str]:
    """File chunks first -- they carry the layouts the functions are judged
    against and call nothing. Then DFS postorder over the call graph, which
    emits every callee before its caller. Cycles have no valid order; the walk
    breaks them so each member still appears exactly once."""
    edges = _call_graph(chunks, links)
    sort_key = _sort_key

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


def call_levels(chunks: Sequence[Chunk], links: Sequence[Link]) -> dict[str, int]:
    """How deep each chunk sits in the call graph. A leaf is 0.

    A chunk's level is one more than its deepest callee, so a caller always
    outranks everything it calls, and therefore no two chunks sharing a level can
    call each other. That is the whole point: a level is a set of chunks that may
    be inspected concurrently without any of them needing another's note.

    File chunks are 0. They call nothing and are inspected first regardless.

    A cycle has no depth. The walk breaks it the way :func:`inspection_order`
    does -- by ignoring an edge that runs back onto the current path -- which
    gives every member a level and leaves at least one of them below the others.
    """
    edges = _call_graph(chunks, links)
    levels: dict[str, int] = {c.chunk_id: 0 for c in chunks if c.kind == FILE_CHUNK_KIND}
    on_path: set[str] = set()

    def visit(start: str) -> None:
        # Iterative, for the same reason the ordering walk is: a deep call chain
        # would otherwise blow the recursion limit.
        stack: list[tuple[str, bool]] = [(start, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                on_path.discard(node)
                below = [levels[callee] for callee in edges.get(node, []) if callee in levels and callee != node]
                levels[node] = 1 + max(below) if below else 0
                continue
            if node in levels or node in on_path:
                continue
            on_path.add(node)
            stack.append((node, True))
            for neighbour in reversed(edges.get(node, [])):
                if neighbour not in levels and neighbour not in on_path:
                    stack.append((neighbour, False))

    for chunk in sorted((c for c in chunks if c.kind != FILE_CHUNK_KIND), key=_sort_key):
        visit(chunk.chunk_id)

    return levels


def wave(
    pending: Sequence[str],
    levels: Mapping[str, int],
    width: int,
    affinity: Mapping[str, int] | None = None,
) -> list[str]:
    """The head of the queue, plus everything after it at the same level.

    Bounded by ``width`` so a flat tree of four hundred leaves does not become
    four hundred requests in flight. Reading *along* the queue rather than
    re-sorting it keeps the run's order the order the index wrote down, which is
    what makes two runs of the same tree comparable.

    ``affinity`` -- the knowledge graph's subsystems, in practice -- decides who
    joins the head when there are more candidates than room. Filling a wave with
    the head's own subsystem means a specialist reads four related functions
    rather than four strangers, and their shared callees are already in the
    context cache. Chunks outside it still fill the remaining space; this is a
    preference, not a partition.

    A chunk with no recorded level (an index written before levels existed) is
    given a wave of its own, which is the old one-at-a-time behaviour.
    """
    if not pending or width <= 1:
        return list(pending[:1])
    head = pending[0]
    if head not in levels:
        return [head]

    depth = levels[head]
    candidates = [chunk_id for chunk_id in pending[1:] if levels.get(chunk_id) == depth]
    if affinity:
        home = affinity.get(head)
        # Stable: `sorted` keeps queue order inside each group, so the run still
        # follows the order the index wrote down.
        candidates.sort(key=lambda chunk_id: affinity.get(chunk_id) != home)
    return [head, *candidates[: width - 1]]
