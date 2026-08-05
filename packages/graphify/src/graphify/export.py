"""The graph as something to hand on: a JSON document, or a page to look at.

The page is self-contained -- no CDN, no fonts, no fetch. It is written into a
run directory beside the code it describes, and a visualisation that only works
with a network connection is not a visualisation of a local run.
"""

from __future__ import annotations

import json
from typing import Any

from .communities import Community
from .model import KnowledgeGraph


def to_json(graph: KnowledgeGraph, communities: list[Community]) -> dict[str, Any]:
    """Everything, in one document. The shape the API and the studio read."""
    community_of = {member: c.id for c in communities for member in c.members}
    payload = graph.to_json()
    for node in payload["nodes"]:
        node["community"] = community_of.get(node["id"])
    payload["communities"] = [c.to_json() for c in communities]
    payload["counts"] = {
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "communities": len(communities),
        "inferred": sum(1 for e in graph.edges if e.provenance == "inferred"),
    }
    return payload


_PAGE = """<!doctype html>
<meta charset="utf-8">
<title>%(title)s</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; font: 14px/1.6 ui-sans-serif, system-ui, sans-serif; }
  header { padding: 16px 20px; border-bottom: 1px solid color-mix(in oklch, currentColor 15%%, transparent); }
  h1 { margin: 0 0 4px; font-size: 18px; }
  .muted { opacity: 0.65; font-size: 13px; }
  main { display: grid; grid-template-columns: minmax(0, 1fr); gap: 12px; padding: 20px; }
  section { border: 1px solid color-mix(in oklch, currentColor 15%%, transparent); border-radius: 8px; padding: 12px 16px; }
  h2 { margin: 0 0 8px; font-size: 15px; }
  ul { margin: 0; padding-left: 18px; }
  code { font-family: ui-monospace, monospace; font-size: 12.5px; }
  .files { opacity: 0.7; font-size: 12.5px; }
</style>
<header>
  <h1>%(title)s</h1>
  <p class="muted">%(nodes)d nodes, %(edges)d edges (%(inferred)d inferred), %(communities)d subsystems</p>
</header>
<main>%(body)s</main>
"""


def to_html(graph: KnowledgeGraph, communities: list[Community], title: str = "Knowledge graph") -> str:
    """A readable page: the subsystems, and what is in each.

    Not a force-directed picture. A hairball of two thousand nodes is a
    screensaver; the useful question is "what groups exist and what is in them",
    and that is a list.
    """
    sections = []
    for community in communities:
        members = "".join(
            f"<li><code>{_escape(graph.nodes[m].label)}</code> "
            f'<span class="files">{_escape(graph.nodes[m].file)}</span></li>'
            for m in community.members
            if m in graph.nodes
        )
        sections.append(
            f"<section><h2>{community.id}. {_escape(community.label)}</h2>"
            f'<p class="files">{_escape(", ".join(community.files))}</p>'
            f"<ul>{members}</ul></section>"
        )

    return _PAGE % {
        "title": _escape(title),
        "nodes": len(graph.nodes),
        "edges": len(graph.edges),
        "inferred": sum(1 for e in graph.edges if e.provenance == "inferred"),
        "communities": len(communities),
        "body": "".join(sections) or "<section><p>Nothing indexed.</p></section>",
    }


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write(path_json: Any, graph: KnowledgeGraph, communities: list[Community]) -> None:
    path_json.parent.mkdir(parents=True, exist_ok=True)
    path_json.write_text(json.dumps(to_json(graph, communities), indent=2), encoding="utf-8")
