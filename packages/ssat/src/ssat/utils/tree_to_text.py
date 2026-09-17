from typing import Any, List, Mapping, Optional, Set

from ..types.node import TemplateNodes


class TreeToText:
    def __init__(self, blacklist_props: Optional[List[str]] = None):
        self.blacklist_props: Set[str] = set(blacklist_props or [])

    def convert(self, root: TemplateNodes) -> str:
        lines: List[str] = []
        self._build_lines(root, "", True, lines, 0)
        return "\n".join(lines)

    def _build_lines(self, node: Mapping[str, Any], prefix: str, is_last: bool, lines: List[str], depth: int) -> None:
        type_name = "Unknown"
        for key in ("nodeType", "label"):
            value = node.get(key)
            if isinstance(value, str) and value:
                type_name = value
                break

        connector = "" if depth == 0 else ("└── " if is_last else "├── ")
        attr_text = self._format_attributes(node)
        lines.append(f"{prefix}{connector}{type_name}{attr_text}")

        new_prefix = "" if depth == 0 else prefix + ("    " if is_last else "│   ")
        children = node.get("children", [])
        if not isinstance(children, list):
            children = []

        for idx, child in enumerate(children):
            last = idx == len(children) - 1
            self._build_lines(child, new_prefix, last, lines, depth + 1)

    def _format_attributes(self, node: Mapping[str, Any]) -> str:
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
                str_val = str(value)

            parts.append(f"{key}={str_val}")

        if not parts:
            return ""
        return f" ({', '.join(parts)})"
