"""Which parts of a tree belong together, found rather than declared.

Directories say where someone filed a thing; the call graph says what actually
depends on what. A community is the second answer, and it is the one that
matters when the question is "what else should I be reading".

Label propagation, not Louvain, and no networkx. The graph is a few thousand
nodes at most, this runs once per index, and a dependency pulled in for a single
function call is a dependency to keep up to date forever. What that costs is
some partition quality; what it buys is that this is fifty lines you can read.

Determinism is not optional here. The partition decides how work is grouped, so
a run that clustered differently on a second pass would inspect the same tree in
a different order and produce a report that could not be diffed against the
first. Ties break on the node id, and the sweep order is fixed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Sequence

from .model import KnowledgeGraph

#: Enough for a partition to settle on graphs this size; the loop exits early
#: the moment nothing moves, which is the usual case well before this.
MAX_SWEEPS = 20


@dataclass(frozen=True)
class Community:
    """A cluster, and the plainest description of it we can honestly give."""

    id: int
    label: str
    members: tuple[str, ...]
    files: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "label": self.label, "members": list(self.members), "files": list(self.files)}


def detect(graph: KnowledgeGraph, kinds: Sequence[str] | None = None) -> list[Community]:
    """Partition the graph. Every node lands in exactly one community.

    ``kinds`` restricts which relationships get a vote, and for source code it
    matters more than anything else here. Left open, a shared header that every
    file includes is a node joined to the whole tree, and the answer comes back
    as one community containing everything -- which is true, useless, and what
    this returned before the parameter existed. Passing the relationship that
    means dependency (``("calls",)`` for code) is what makes the clusters say
    something.
    """
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

    # Numbered by size, largest first, so community 0 is the one worth reading
    # about first and the numbering does not shuffle when a leaf is added.
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
    """The label most of this node's structural neighbours carry.

    Inferred edges do not vote at all. Weighting them down was tried first and
    is not enough: a README naming forty symbols is a node with forty edges, and
    a hub that size drags everything it mentions into one community whatever the
    weight. Mentions stay in the graph, where `graph_neighbours` will happily
    report them -- they are just not evidence about what belongs with what.

    Ties go to the smallest label, which is what makes the sweep reproducible.
    """
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
    """Name a community after its busiest member, falling back to its file.

    Not a summary -- naming a cluster properly would take a model, and this has
    to be free. The most-connected symbol is a decent handle in practice.
    """
    busiest = max(members, key=lambda node_id: (len(graph.adjacent(node_id)), node_id))
    node = graph.nodes[busiest]
    return node.label or node.file or busiest


def subsystem_of(communities: list[Community], node_id: str) -> Community | None:
    return next((c for c in communities if node_id in c.members), None)
