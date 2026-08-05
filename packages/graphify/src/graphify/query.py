"""Turning a traversal into something worth putting in a prompt.

The graph answers in nodes; a model needs prose, and a bounded amount of it.
Every function here takes a character budget and stays inside it, because the
caller is a tool the model invokes mid-run and an answer that blows the context
window is worse than no answer.
"""

from __future__ import annotations

from .communities import Community, subsystem_of
from .model import Direction, KnowledgeGraph, Node

#: What a tool answer is allowed to cost. Roughly a page.
DEFAULT_BUDGET = 4_000


def _line(graph: KnowledgeGraph, node: Node, relation: str = "") -> str:
    where = f" ({node.file})" if node.file else ""
    kind = f"[{node.kind}] " if node.kind else ""
    prefix = f"{relation}: " if relation else ""
    return f"- {prefix}{kind}{node.label}{where}"


def _bounded(lines: list[str], budget: int, total: int) -> str:
    """Join what fits, and say plainly what did not.

    Truncating in silence is the failure mode that matters: a model told "these
    are the neighbours" will reason as though the list were complete.
    """
    kept: list[str] = []
    spent = 0
    for line in lines:
        if spent + len(line) + 1 > budget:
            break
        kept.append(line)
        spent += len(line) + 1
    if len(kept) < total:
        kept.append(f"... and {total - len(kept)} more, not shown (budget {budget} characters)")
    return "\n".join(kept)


def describe_neighbours(
    graph: KnowledgeGraph,
    node_id: str,
    hops: int = 1,
    direction: Direction = "both",
    budget: int = DEFAULT_BUDGET,
) -> str:
    if node_id not in graph.nodes:
        return f"no such node: {node_id}"

    node = graph.nodes[node_id]
    found = graph.neighbours(node_id, hops=hops, direction=direction)
    if not found:
        return f"{node.label} is connected to nothing else in this tree."

    header = f"{node.label}{f' ({node.file})' if node.file else ''} -- {len(found)} within {hops} hop(s):"
    body = _bounded([_line(graph, n) for n in found], budget - len(header) - 1, len(found))
    return f"{header}\n{body}"


def describe_path(graph: KnowledgeGraph, start: str, end: str, budget: int = DEFAULT_BUDGET) -> str:
    trail = graph.path(start, end)
    if not trail:
        return "no path between them in this tree."
    header = f"{len(trail)} step(s):"
    body = _bounded([_line(graph, n) for n in trail], budget - len(header) - 1, len(trail))
    return f"{header}\n{body}"


def describe_subsystem(
    graph: KnowledgeGraph,
    communities: list[Community],
    node_id: str,
    budget: int = DEFAULT_BUDGET,
) -> str:
    community = subsystem_of(communities, node_id)
    if community is None:
        return f"no such node: {node_id}"

    header = (
        f"subsystem {community.id} '{community.label}' -- "
        f"{len(community.members)} unit(s) across {len(community.files)} file(s): "
        f"{', '.join(community.files[:12])}"
    )
    members = [graph.nodes[m] for m in community.members if m in graph.nodes and m != node_id]
    body = _bounded([_line(graph, n) for n in members], budget - len(header) - 1, len(members))
    return f"{header}\n{body}"
