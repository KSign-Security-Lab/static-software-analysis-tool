"""AST utility functions."""

from typing import List

from ..types.node import TemplateNodes
from ..types.template.BaseNode.base_types import TemplateNodeTypes

INVALID_FUNCTION_NAMES = ["", "<clinit>", "<empty>"]


def recursively_get_functions_from_template(template: List[TemplateNodes]) -> List[TemplateNodes]:
    """
    Recursively extract function definitions from template nodes.

    Filters for:
    - FunctionDefinition node type
    - Non-invalid function names
    - Functions with children
    - Functions with names matching "bad", "good", or "sink" (case-insensitive)

    Args:
        template: List of template nodes to search.

    Returns:
        List of function definition nodes matching the criteria.
    """
    import re

    functions: List[TemplateNodes] = []

    def collect_functions(nodes: List[TemplateNodes]) -> None:
        """Recursively collect function nodes."""
        for node in nodes:
            if isinstance(node, dict):
                node_type = node.get("nodeType")
                name = node.get("name", "")
                children = node.get("children", [])

                if node_type == TemplateNodeTypes.FunctionDefinition:
                    if (
                        name not in INVALID_FUNCTION_NAMES
                        and isinstance(children, list)
                        and len(children) > 0
                        and re.search(r"bad|good|sink", name, re.IGNORECASE)
                    ):
                        functions.append(node)

                if isinstance(children, list):
                    collect_functions(children)
            else:
                # Handle object with attributes
                node_type = getattr(node, "nodeType", None)
                name = getattr(node, "name", "")
                children = getattr(node, "children", [])

                if node_type == TemplateNodeTypes.FunctionDefinition:
                    if (
                        name not in INVALID_FUNCTION_NAMES
                        and isinstance(children, list)
                        and len(children) > 0
                        and re.search(r"bad|good|sink", name, re.IGNORECASE)
                    ):
                        functions.append(node)

                if isinstance(children, list):
                    collect_functions(children)

    collect_functions(template)
    return functions

