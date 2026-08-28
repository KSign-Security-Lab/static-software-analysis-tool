"""The run's index, as a knowledge graph.

The adapter, and the only place the two packages meet. ``graphify`` knows
nothing about chunks or SQLite -- it takes records -- so the translation lives
here, on the side that already knows both. That keeps the dependency running one
way: the agent uses graphify, graphify never reaches back.

Built once per index and cached beside it. Building is a pass over rows and a
text scan, so it costs milliseconds and no model call, but the MCP tools call in
per question and rebuilding each time would be silly.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from graphify import Community, Edge, KnowledgeGraph, Node, build, detect
from graphify import to_json as graph_json

from .index.chunk import FILE_CHUNK_KIND
from .index.links import CALLS
from .index.store import ChunkStore

log = logging.getLogger(__name__)

#: What counts as "belongs with" when clustering source. Calls, and only calls:
#: `file_depends` on a header every file includes joins the whole tree into one
#: community, which is true and tells you nothing.
CLUSTER_ON = (CALLS,)

#: Beside `index.db`, so a run's map lives and dies with the run it describes.


def records(store: ChunkStore) -> tuple[list[Node], list[Edge]]:
    """Chunks and links, as graphify's records."""
    nodes = [
        Node(
            id=chunk.chunk_id,
            kind="file" if chunk.kind == FILE_CHUNK_KIND else "unit",
            label=chunk.symbol,
            file=chunk.file,
            attrs={"start_line": chunk.start_line, "end_line": chunk.end_line},
        )
        for chunk in store.chunks()
    ]
    edges = [Edge(src=link.src, dst=link.dst, kind=link.kind) for link in store.links()]
    return nodes, edges


def build_graph(store: ChunkStore, root: Path | None = None) -> KnowledgeGraph:
    return build(*records(store), root=root)


def write_graph(store: ChunkStore) -> dict[str, Any]:
    """Build the graph for a run and store it on the run. Returns the counts.

    Was `graph.json` beside the index. It is one JSONB column on the run row
    now, which is what it always was: one derived document per run.
    """
    graph = build_graph(store)
    communities = detect(graph, CLUSTER_ON)
    payload = graph_json(graph, communities)

    from .db import Run as RunRow
    from .db import session_scope

    with session_scope() as session:
        row = session.get(RunRow, store.run_id)
        if row is not None:
            row.knowledge = payload
    counts: dict[str, Any] = payload["counts"]
    return counts


def read_graph(run_id: str) -> tuple[KnowledgeGraph, list[Community]] | None:
    """The stored graph, or nothing if this run has none."""
    from .db import Run as RunRow
    from .db import session_scope

    with session_scope() as session:
        row = session.get(RunRow, run_id)
        payload = row.knowledge if row else None
    if not payload:
        return None
    graph = KnowledgeGraph.from_json(payload)
    communities = [
        Community(
            id=int(c["id"]),
            label=str(c.get("label", "")),
            members=tuple(c.get("members", ())),
            files=tuple(c.get("files", ())),
        )
        for c in payload.get("communities", [])
    ]
    return graph, communities


def load_or_build(store: ChunkStore) -> tuple[KnowledgeGraph, list[Community]]:
    """What the tools use: the stored graph, or one built on the spot.

    Built rather than refused when it is missing, because a run indexed before
    this existed still deserves working tools.
    """
    cached = read_graph(store.run_id)
    if cached is not None:
        return cached
    graph = build_graph(store)
    return graph, detect(graph, CLUSTER_ON)


def find(graph: KnowledgeGraph, symbol: str) -> str | None:
    """A node id for a symbol as a person would type it.

    Exact label first, then a file path, then a unique case-insensitive match.
    Ambiguity resolves to the best-connected candidate: with two `init`s, the
    one everything calls is the one being asked about.
    """
    if symbol in graph.nodes:
        return symbol

    exact = [n for n in graph.nodes.values() if n.label == symbol]
    if not exact:
        exact = [n for n in graph.nodes.values() if n.file == symbol]
    if not exact:
        lowered = symbol.lower()
        exact = [n for n in graph.nodes.values() if n.label.lower() == lowered]
    if not exact:
        return None
    return max(exact, key=lambda n: (len(graph.adjacent(n.id)), n.id)).id
