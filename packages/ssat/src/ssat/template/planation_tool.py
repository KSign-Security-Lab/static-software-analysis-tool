from typing import Dict, List, Optional, Set

from ..types.node import TemplateFlattenedGraph, TemplateNodes
from ..types.template.BaseNode.base_types import TemplateNodeTypes


class PlanationTool:
    def __init__(self, blacklist: Optional[List[TemplateNodeTypes]] = None):
        self.blacklist: Set[TemplateNodeTypes] = set(blacklist) if blacklist else set()
        self.edges: List[Dict[str, int]] = []
        self.nodes: List[TemplateNodes] = []

    def flatten(self, ast_roots: List[TemplateNodes], remove_blacklist: bool = False) -> List[TemplateFlattenedGraph]:
        graphs: List[TemplateFlattenedGraph] = []

        for root in ast_roots:
            self._reset()
            self._traverse(root)

            self.nodes.sort(key=lambda n: n.get("id", 0) if isinstance(n, dict) else getattr(n, "id", 0))
            self.edges.sort(key=lambda e: e["from"] + e["to"])

            self._validate_edges()

            graphs.append(
                {
                    "edges": self.edges.copy(),
                    "nodes": self.nodes.copy(),
                }
            )

        if remove_blacklist:
            for graph in graphs:
                graph["nodes"] = [node for node in graph["nodes"] if self._get_node_type(node) not in self.blacklist]
                node_ids = {self._get_node_id(node) for node in graph["nodes"]}
                graph["edges"] = [
                    edge for edge in graph["edges"] if edge["from"] in node_ids and edge["to"] in node_ids
                ]

        return graphs

    def _reset(self) -> None:
        self.edges = []
        self.nodes = []

    def _traverse(self, node: TemplateNodes) -> int:
        node_dict = node if isinstance(node, dict) else node.__dict__
        children = node_dict.get("children", [])
        node_id = node_dict.get("id", 0) if isinstance(node, dict) else getattr(node, "id", 0)
        clone = {k: v for k, v in node_dict.items() if k != "children"}
        clone["id"] = node_id
        self.nodes.append(clone)  # type: ignore

        if isinstance(children, list):
            for child in children:
                child_id = self._traverse(child)
                self.edges.append({"from": node_id, "to": child_id})

        return node_id

    def _validate_edges(self) -> None:
        existing_ids = {self._get_node_id(node) for node in self.nodes}
        for edge in self.edges:
            if edge["from"] not in existing_ids:
                raise ValueError(f"Edge refers to unknown source node id {edge['from']}")
            if edge["to"] not in existing_ids:
                raise ValueError(f"Edge refers to unknown target node id {edge['to']}")

    def _get_node_id(self, node: TemplateNodes) -> int:
        if isinstance(node, dict):
            return node.get("id", 0)
        return getattr(node, "id", 0)

    def _get_node_type(self, node: TemplateNodes) -> Optional[TemplateNodeTypes]:
        if isinstance(node, dict):
            return node.get("nodeType")
        return getattr(node, "nodeType", None)
