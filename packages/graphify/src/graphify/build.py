from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from .model import Edge, KnowledgeGraph, Node

DOC_SUFFIXES = frozenset({".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".conf"})
DOC_NAMES = frozenset({"Makefile", "Dockerfile", "CMakeLists.txt"})
MAX_DOC_BYTES = 200_000
MIN_SYMBOL_CHARS = 4


def is_document(path: Path) -> bool:
    return path.name in DOC_NAMES or path.suffix.lower() in DOC_SUFFIXES


def build(nodes: Iterable[Node], edges: Iterable[Edge], root: Path | None = None) -> KnowledgeGraph:
    nodes = list(nodes)
    edges = list(edges)
    if root is not None:
        doc_nodes, doc_edges = documents(nodes, root)
        nodes.extend(doc_nodes)
        edges.extend(doc_edges)
    return KnowledgeGraph(nodes, edges)


def documents(nodes: Sequence[Node], root: Path) -> tuple[list[Node], list[Edge]]:
    by_symbol: dict[str, list[str]] = {}
    for node in nodes:
        label = node.label
        if len(label) >= MIN_SYMBOL_CHARS and label.isidentifier():
            by_symbol.setdefault(label, []).append(node.id)
    if not by_symbol:
        return [], []

    pattern = re.compile(r"\b(" + "|".join(re.escape(s) for s in sorted(by_symbol, key=len, reverse=True)) + r")\b")
    doc_nodes: list[Node] = []
    doc_edges: list[Edge] = []

    for path in sorted(p for p in root.rglob("*") if p.is_file() and is_document(p)):
        try:
            if path.stat().st_size > MAX_DOC_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        relative = path.relative_to(root).as_posix()
        mentioned = sorted(set(pattern.findall(text)))
        if not mentioned:
            continue

        doc_id = f"doc:{relative}"
        doc_nodes.append(Node(id=doc_id, kind="doc", label=relative, file=relative))
        for symbol in mentioned:
            for target in by_symbol[symbol]:
                doc_edges.append(Edge(src=doc_id, dst=target, kind="mentions", provenance="inferred"))

    return doc_nodes, doc_edges
