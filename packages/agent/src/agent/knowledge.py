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
CLUSTER_ON = (CALLS,)


def records(store: ChunkStore) -> tuple[list[Node], list[Edge]]:
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
    cached = read_graph(store.run_id)
    if cached is not None:
        return cached
    graph = build_graph(store)
    return graph, detect(graph, CLUSTER_ON)


def find(graph: KnowledgeGraph, symbol: str) -> str | None:
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
