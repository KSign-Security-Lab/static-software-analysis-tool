"""Assembling a graph, including the parts of a tree a parser never sees.

The structural half comes in as records: whoever indexed the code already
resolved which unit calls which, and re-deriving that here would be a second
answer to a settled question.

The other half is what tree-sitter skips entirely -- READMEs, configs, build
files, specs. Those name symbols in prose, and a mention is a real relationship
even though it is a weak one. It is drawn as an `inferred` edge and is marked as
such everywhere it surfaces, so nothing downstream can mistake "this file talks
about `handle_download`" for "this file calls `handle_download`".
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Sequence

from .model import Edge, KnowledgeGraph, Node

#: Files worth reading for mentions. Not source -- source is already indexed --
#: and not anything that would take a parser.
DOC_SUFFIXES = frozenset({".md", ".rst", ".txt", ".toml", ".yaml", ".yml", ".json", ".ini", ".cfg", ".conf"})
DOC_NAMES = frozenset({"Makefile", "Dockerfile", "CMakeLists.txt"})

#: A document over this is a data file, not prose about the code.
MAX_DOC_BYTES = 200_000

#: Below this a "mention" is noise: `id`, `fd`, `n` appear in every sentence.
MIN_SYMBOL_CHARS = 4


def is_document(path: Path) -> bool:
    return path.name in DOC_NAMES or path.suffix.lower() in DOC_SUFFIXES


def build(nodes: Iterable[Node], edges: Iterable[Edge], root: Path | None = None) -> KnowledgeGraph:
    """The structural graph, plus mentions from the tree's documents."""
    nodes = list(nodes)
    edges = list(edges)
    if root is not None:
        doc_nodes, doc_edges = documents(nodes, root)
        nodes.extend(doc_nodes)
        edges.extend(doc_edges)
    return KnowledgeGraph(nodes, edges)


def documents(nodes: Sequence[Node], root: Path) -> tuple[list[Node], list[Edge]]:
    """Document nodes, and an inferred edge per symbol each one names."""
    by_symbol: dict[str, list[str]] = {}
    for node in nodes:
        label = node.label
        if len(label) >= MIN_SYMBOL_CHARS and label.isidentifier():
            by_symbol.setdefault(label, []).append(node.id)
    if not by_symbol:
        return [], []

    # One pass over each document with one alternation, rather than one scan per
    # symbol: a tree with two thousand symbols and forty documents is eighty
    # thousand scans done the obvious way.
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
