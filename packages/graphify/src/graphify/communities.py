from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Sequence

from .model import KnowledgeGraph

MAX_SWEEPS = 20


@dataclass(frozen=True)
class Community:
    id: int
    label: str
    members: tuple[str, ...]
    files: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "members": list(self.members), "files": list(self.files)}


def detect(graph: KnowledgeGraph, kinds: Sequence[str] | None = None) -> list[Community]:
    if not graph.nodes:
        return []

    allowed = frozenset(kinds) if kinds is not None else None
    order = sorted(graph.nodes)
    label = {node_id: node_id for node_id in order}

    for _ in range(MAX_SWEEPS):
        moved = False
        for node_id in order:
            best = _most_common_neighbour_label(graph, label, node_id, allowed)
            if best is not None and best != label[node_id]:
                label[node_id] = best
                moved = True
        if not moved:
            break

    grouped: dict[str, list[str]] = defaultdict(list)
    for node_id in order:
        grouped[label[node_id]].append(node_id)

    ranked = sorted(grouped.values(), key=lambda members: (-len(members), members[0]))
    return [
        Community(
            id=index,
            label=_label_for(graph, members),
            members=tuple(members),
            files=tuple(sorted({graph.nodes[m].file for m in members if graph.nodes[m].file})),
        )
        for index, members in enumerate(ranked)
    ]


def _most_common_neighbour_label(
    graph: KnowledgeGraph,
    label: dict[str, str],
    node_id: str,
    allowed: frozenset[str] | None,
) -> str | None:
    counts: dict[str, int] = defaultdict(int)
    for edge in graph.adjacent(node_id):
        if edge.provenance != "extracted":
            continue
        if allowed is not None and edge.kind not in allowed:
            continue
        other = edge.dst if edge.src == node_id else edge.src
        counts[label[other]] += 1
    if not counts:
        return None
    return min(counts, key=lambda name: (-counts[name], name))


def _label_for(graph: KnowledgeGraph, members: list[str]) -> str:
    busiest = max(members, key=lambda node_id: (len(graph.adjacent(node_id)), node_id))
    node = graph.nodes[busiest]
    return node.label or node.file or busiest


def subsystem_of(communities: list[Community], node_id: str) -> Community | None:
    return next((c for c in communities if node_id in c.members), None)
