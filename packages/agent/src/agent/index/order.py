from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

from .chunk import FILE_CHUNK_KIND, Chunk
from .links import CALLS, Link


def _sort_key(chunk: Chunk) -> tuple[str, int, str]:
    return (chunk.file, chunk.start_line, chunk.chunk_id)


def _call_graph(chunks: Sequence[Chunk], links: Sequence[Link]) -> dict[str, list[str]]:
    known = {chunk.chunk_id for chunk in chunks}
    edges: dict[str, list[str]] = defaultdict(list)
    for link in links:
        if link.kind == CALLS and link.src in known and link.dst in known:
            edges[link.src].append(link.dst)
    for targets in edges.values():
        targets.sort()
    return edges


def inspection_order(chunks: Sequence[Chunk], links: Sequence[Link]) -> list[str]:
    edges = _call_graph(chunks, links)
    sort_key = _sort_key
    files = sorted((c for c in chunks if c.kind == FILE_CHUNK_KIND), key=sort_key)
    functions = sorted((c for c in chunks if c.kind != FILE_CHUNK_KIND), key=sort_key)
    order: list[str] = [chunk.chunk_id for chunk in files]
    emitted = set(order)
    on_path: set[str] = set()

    def visit(start: str) -> None:
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
    edges = _call_graph(chunks, links)
    levels: dict[str, int] = {c.chunk_id: 0 for c in chunks if c.kind == FILE_CHUNK_KIND}
    on_path: set[str] = set()

    def visit(start: str) -> None:
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


# Edges pointing forward in the order are exactly the cycle edges -- the traversal
# above meets those chunks already on its own path. Dropping them here is what makes
# readiness a partial order, and so what makes a round impossible to deadlock.
def blockers(order: Sequence[str], links: Sequence[Link]) -> dict[str, tuple[str, ...]]:
    position = {chunk_id: index for index, chunk_id in enumerate(order)}
    found: dict[str, set[str]] = defaultdict(set)
    for link in links:
        if link.kind != CALLS:
            continue
        src, dst = link.src, link.dst
        if src == dst or src not in position or dst not in position:
            continue
        if position[dst] < position[src]:
            found[src].add(dst)
    return {chunk_id: tuple(sorted(found[chunk_id])) for chunk_id in order if found.get(chunk_id)}


# A blocker still in `pending` has not written its note yet. While pending keeps the
# computed order the head is always ready -- its blockers all sit before it, so they
# have left the queue -- and a round is never empty. Advisory planning may reorder the
# queue and break that, so the head goes alone rather than stalling.
def ready(
    pending: Sequence[str],
    blocked: Mapping[str, Sequence[str]],
    width: int,
    affinity: Mapping[str, int] | None = None,
) -> list[str]:
    if not pending:
        return []
    if width <= 1:
        return list(pending[:1])

    waiting = set(pending)
    free = [chunk_id for chunk_id in pending if not waiting.intersection(blocked.get(chunk_id, ()))]
    if not free:
        return list(pending[:1])

    head, *rest = free
    if affinity:
        home = affinity.get(head)
        rest.sort(key=lambda chunk_id: affinity.get(chunk_id) != home)
    return [head, *rest[: width - 1]]
