"""Planation tool for flattening template nodes into graphs."""

from typing import Dict, List, Optional, Set

from ..types.node import TemplateFlattenedGraph, TemplateNodes
from ..types.template.BaseNode.base_types import TemplateNodeTypes


class PlanationTool:
    """Tool for flattening template nodes into graph structures."""

    def __init__(self, blacklist: List[TemplateNodeTypes] = None):
        """Initialize planation tool."""
        self.blacklist: Set[TemplateNodeTypes] = set(blacklist) if blacklist else set()
        self.edges: List[Dict[str, int]] = []
        self.nodes: List[TemplateNodes] = []

    def flatten(self, ast_roots: List[TemplateNodes], remove_blacklist: bool = False) -> List[TemplateFlattenedGraph]:
        """Given an array of root ASTNodes, returns one ASTFlattenedGraph per root."""
        graphs: List[TemplateFlattenedGraph] = []

        for root in ast_roots:
            self._reset()
            self._traverse(root)

            # Sort nodes by ascending id
            self.nodes.sort(key=lambda n: n.get("id", 0) if isinstance(n, dict) else getattr(n, "id", 0))
            # Sort edges by ascending sum of from+to
            self.edges.sort(key=lambda e: e["from"] + e["to"])

            # Sanity-check that every edge references existing node ids
            self._validate_edges()

            graphs.append({
                "edges": self.edges.copy(),
                "nodes": self.nodes.copy(),
            })

        if remove_blacklist:
            # Filter out blacklisted nodes
            for graph in graphs:
                graph["nodes"] = [node for node in graph["nodes"] if self._get_node_type(node) not in self.blacklist]
                node_ids = {self._get_node_id(node) for node in graph["nodes"]}
                graph["edges"] = [edge for edge in graph["edges"] if edge["from"] in node_ids and edge["to"] in node_ids]

        return graphs

    def _reset(self) -> None:
        """Reset all internal state before processing a new root."""
        self.edges = []
        self.nodes = []

    def _traverse(self, node: TemplateNodes) -> int:
        """Walk the AST recursively, strip children, assign each node a unique id."""
        node_dict = node if isinstance(node, dict) else node.__dict__
        children = node_dict.get("children", [])
        node_id = node_dict.get("id", 0) if isinstance(node, dict) else getattr(node, "id", 0)

        # Clone node minus its children, attach id
        clone = {k: v for k, v in node_dict.items() if k != "children"}
        clone["id"] = node_id
        self.nodes.append(clone)  # type: ignore

        if isinstance(children, list):
            for child in children:
                child_id = self._traverse(child)
                self.edges.append({"from": node_id, "to": child_id})

        return node_id

    def _validate_edges(self) -> None:
        """Verify that each edge's from and to refer to an actual node ID."""
        existing_ids = {self._get_node_id(node) for node in self.nodes}
        for edge in self.edges:
            if edge["from"] not in existing_ids:
                raise ValueError(f"Edge refers to unknown source node id {edge['from']}")
            if edge["to"] not in existing_ids:
                raise ValueError(f"Edge refers to unknown target node id {edge['to']}")

    def _get_node_id(self, node: TemplateNodes) -> int:
        """Get node ID."""
        if isinstance(node, dict):
            return node.get("id", 0)
        return getattr(node, "id", 0)

    def _get_node_type(self, node: TemplateNodes) -> Optional[TemplateNodeTypes]:
        """Get node type."""
        if isinstance(node, dict):
            return node.get("nodeType")
        return getattr(node, "nodeType", None)

