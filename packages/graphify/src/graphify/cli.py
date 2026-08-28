"""`graphify` on the command line: build a graph, ask it things, export it.

Takes a graph document rather than a source tree, because building one needs an
index and the index belongs to whoever made it. `agent index` writes the
document; this reads it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .communities import Community, detect
from .export import to_html, to_json
from .model import KnowledgeGraph
from .query import describe_neighbours, describe_path, describe_subsystem


def _load(path: Path) -> tuple[KnowledgeGraph, list[Community]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    graph = KnowledgeGraph.from_json(payload)
    stored = payload.get("communities")
    if not stored:
        return graph, detect(graph)
    return graph, [
        Community(
            id=int(c["id"]),
            label=str(c.get("label", "")),
            members=tuple(c.get("members", ())),
            files=tuple(c.get("files", ())),
        )
        for c in stored
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="graphify", description=__doc__)
    parser.add_argument("graph", type=Path, help="a graph.json, as written beside a run's index")
    sub = parser.add_subparsers(dest="command", required=True)

    show = sub.add_parser("show", help="the subsystems, largest first")
    show.add_argument("--limit", type=int, default=20)

    near = sub.add_parser("near", help="what a node connects to")
    near.add_argument("node")
    near.add_argument("--hops", type=int, default=1)

    between = sub.add_parser("between", help="the shortest way from one node to another")
    between.add_argument("start")
    between.add_argument("end")

    around = sub.add_parser("around", help="the subsystem a node belongs to")
    around.add_argument("node")

    export = sub.add_parser("export", help="write a self-contained page")
    export.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)
    if not args.graph.exists():
        print(f"no such graph: {args.graph}", file=sys.stderr)
        return 2

    graph, communities = _load(args.graph)

    if args.command == "show":
        counts = to_json(graph, communities)["counts"]
        print(f"{counts['nodes']} nodes, {counts['edges']} edges, {counts['communities']} subsystems")
        for community in communities[: args.limit]:
            print(f"  {community.id:>3}. {community.label} -- {len(community.members)} unit(s)")
            print(f"       {', '.join(community.files[:8])}")
    elif args.command == "near":
        print(describe_neighbours(graph, args.node, hops=args.hops))
    elif args.command == "between":
        print(describe_path(graph, args.start, args.end))
    elif args.command == "around":
        print(describe_subsystem(graph, communities, args.node))
    elif args.command == "export":
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(to_html(graph, communities), encoding="utf-8")
        print(f"wrote {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
