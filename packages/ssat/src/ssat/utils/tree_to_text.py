"""Tree to text conversion utility."""

from typing import Any, Dict, List, Set, Union

from ..types.cpg import TreeNode
from ..types.node import TemplateNodes


class TreeToText:
    """Convert template tree to text representation."""

    def __init__(self, blacklist_props: List[str] = None):
        """
        Initialize TreeToText.

        Args:
            blacklist_props: List of node property names to exclude from text output.
                           Defaults to empty list (no extra keys blacklisted).
        """
        self.blacklist_props: Set[str] = set(blacklist_props or [])

    def convert(self, root: TemplateNodes) -> str:
        """
        Convert a TemplateNodes tree into a text tree.

        Args:
            root: Root node of the template tree.

        Returns:
            String representation of the tree.
        """
        lines: List[str] = []
        self._build_lines(root, "", True, lines, 0)
        return "\n".join(lines)

    def _build_lines(
        self, node: Union[TemplateNodes, TreeNode], prefix: str, is_last: bool, lines: List[str], depth: int
    ) -> None:
        """
        Recursive helper to build lines.

        Args:
            node: Current node.
            prefix: Accumulated prefix string (spaces and vertical bars).
            is_last: Whether this node is the last child of its parent.
            lines: Collector for output lines.
            depth: Current depth (root=0, children=1, ...).
        """
        type_name: str
        if isinstance(node, dict):
            if "nodeType" in node and isinstance(node["nodeType"], str):
                type_name = node["nodeType"]
            elif "label" in node and isinstance(node["label"], str):
                type_name = node["label"]
            else:
                type_name = "Unknown"
        else:
            # For objects with attributes
            if hasattr(node, "nodeType") and isinstance(getattr(node, "nodeType", None), str):
                type_name = getattr(node, "nodeType")
            elif hasattr(node, "label") and isinstance(getattr(node, "label", None), str):
                type_name = getattr(node, "label")
            else:
                type_name = "Unknown"

        connector = "" if depth == 0 else ("└── " if is_last else "├── ")
        attr_text = self._format_attributes(node)
        lines.append(f"{prefix}{connector}{type_name}{attr_text}")

        new_prefix = "" if depth == 0 else prefix + ("    " if is_last else "│   ")
        children = node.get("children", []) if isinstance(node, dict) else getattr(node, "children", [])
        if not isinstance(children, list):
            children = []

        for idx, child in enumerate(children):
            last = idx == len(children) - 1
            self._build_lines(child, new_prefix, last, lines, depth + 1)

    def _format_attributes(self, node: Union[TemplateNodes, TreeNode]) -> str:
        """
        Format all keys except nodeType, label, children, and any in blacklist_props into "(k=v, ...)".

        Args:
            node: Node to format.

        Returns:
            Formatted attribute string.
        """
        parts: List[str] = []
        node_dict = node if isinstance(node, dict) else node.__dict__ if hasattr(node, "__dict__") else {}

        for key, value in node_dict.items():
            if key in ("nodeType", "label", "children"):
                continue
            if key in self.blacklist_props:
                continue
            if value is None or callable(value):
                continue

            if isinstance(value, (str, int, float, bool)) or value is None:
                str_val = str(value)
            else:
                # Convert to string without deep JSON.stringify to avoid huge output
                str_val = str(value)

            parts.append(f"{key}={str_val}")

        if not parts:
            return ""
        return f" ({', '.join(parts)})"

