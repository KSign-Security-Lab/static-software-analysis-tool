from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

Provenance = Literal["extracted", "inferred"]
Direction = Literal["out", "in", "both"]


@dataclass(frozen=True)
class Node:
    id: str
    kind: str
    label: str
    file: str = ""
    attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    kind: str
    provenance: Provenance = "extracted"


class KnowledgeGraph:
    def __init__(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        self.nodes: dict[str, Node] = {node.id: node for node in nodes}
        self.edges: tuple[Edge, ...] = tuple(
            edge for edge in edges if edge.src in self.nodes and edge.dst in self.nodes
        )

        self._out: dict[str, list[Edge]] = defaultdict(list)
        self._in: dict[str, list[Edge]] = defaultdict(list)
        for edge in self.edges:
            self._out[edge.src].append(edge)
            self._in[edge.dst].append(edge)

    def __len__(self) -> int:
        return len(self.nodes)

    def adjacent(self, node_id: str, direction: Direction = "both") -> list[Edge]:
        out = self._out.get(node_id, []) if direction in ("out", "both") else []
        into = self._in.get(node_id, []) if direction in ("in", "both") else []
        return [*out, *into]

    def neighbours(self, node_id: str, hops: int = 1, direction: Direction = "both") -> list[Node]:
        if node_id not in self.nodes:
            return []

        seen = {node_id}
        frontier = [node_id]
        found: list[Node] = []

        for _ in range(max(0, hops)):
            nxt: list[str] = []
            for current in frontier:
                for edge in self.adjacent(current, direction):
                    other = edge.dst if edge.src == current else edge.src
                    if other in seen:
                        continue
                    seen.add(other)
                    nxt.append(other)
                    found.append(self.nodes[other])
            if not nxt:
                break
            frontier = nxt

        return found

    def path(self, start: str, end: str) -> list[Node]:
        if start not in self.nodes or end not in self.nodes:
            return []
        if start == end:
            return [self.nodes[start]]

        previous: dict[str, str | None] = {start: None}
        queue = [start]
        while queue:
            current = queue.pop(0)
            for edge in self.adjacent(current):
                other = edge.dst if edge.src == current else edge.src
                if other in previous:
                    continue
                previous[other] = current
                if other == end:
                    return [self.nodes[n] for n in _walk_back(previous, end)]
                queue.append(other)
        return []

    def to_json(self) -> dict[str, Any]:
        return {
            "nodes": [
                {
                    "id": n.id,
                    "kind": n.kind,
                    "label": n.label,
                    "file": n.file,
                    **({"attrs": n.attrs} if n.attrs else {}),
                }
                for n in self.nodes.values()
            ],
            "edges": [{"src": e.src, "dst": e.dst, "kind": e.kind, "provenance": e.provenance} for e in self.edges],
        }

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "KnowledgeGraph":
        nodes = [
            Node(
                id=str(n["id"]),
                kind=str(n.get("kind", "")),
                label=str(n.get("label", "")),
                file=str(n.get("file", "")),
                attrs=dict(n.get("attrs") or {}),
            )
            for n in payload.get("nodes", [])
        ]
        edges = [
            Edge(
                src=str(e["src"]),
                dst=str(e["dst"]),
                kind=str(e.get("kind", "")),
                provenance="inferred" if e.get("provenance") == "inferred" else "extracted",
            )
            for e in payload.get("edges", [])
        ]
        return cls(nodes, edges)


def _walk_back(previous: dict[str, str | None], end: str) -> list[str]:
    trail = [end]
    while previous[trail[-1]] is not None:
        parent = previous[trail[-1]]
        assert parent is not None
        trail.append(parent)
    return list(reversed(trail))
