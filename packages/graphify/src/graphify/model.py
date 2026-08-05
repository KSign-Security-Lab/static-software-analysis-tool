"""What a knowledge graph is here: nodes, edges, and where each edge came from.

Deliberately not tied to the agent's index. The graph is built from records the
caller hands over, so this package knows nothing about SQLite, chunks or
findings -- which is what keeps the dependency running one way and lets the same
graph be built from something else later.

Every edge carries its provenance. An edge the parser actually resolved and an
edge inferred from a filename appearing in a README are both useful and are not
the same claim, and a graph that cannot tell them apart is a graph you cannot
reason about.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

#: `extracted` was resolved from structure -- a call the parser matched to a
#: definition. `inferred` is a guess from text, and is never load-bearing.
Provenance = Literal["extracted", "inferred"]

Direction = Literal["out", "in", "both"]


@dataclass(frozen=True)
class Node:
    """One thing in the tree: a unit of code, a file, a type, a document."""

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
    """Nodes, edges, and the traversals worth having.

    Adjacency is built once at construction. Every walk below is breadth-first
    and bounded, because these answer a model's questions during a run: an
    unbounded traversal of a large tree is a way to spend a context window
    saying nothing.
    """

    def __init__(self, nodes: Iterable[Node], edges: Iterable[Edge]) -> None:
        self.nodes: dict[str, Node] = {node.id: node for node in nodes}
        # Edges whose ends are not both present would make a walk step into
        # nothing. Dropped here rather than guarded at every use.
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
        """Everything within ``hops`` steps, nearest first, excluding the start.

        Nearest first because that is the order a reader wants: what this thing
        touches, then what those touch.
        """
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
        """The shortest way from one to the other, or nothing.

        Undirected: "how are these two related" is rarely a question about which
        way the calls point, and a directed answer of "no path" when there is an
        obvious one is worse than useless.
        """
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
