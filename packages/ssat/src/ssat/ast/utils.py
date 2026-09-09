from typing import List

from ..types.node import TemplateNodes
from ..types.template.BaseNode.base_types import TemplateNodeTypes

INVALID_FUNCTION_NAMES = ["", "<clinit>", "<empty>"]


def get_juliet_benchmark_functions(template: List[TemplateNodes]) -> List[TemplateNodes]:
    import re

    functions: List[TemplateNodes] = []

    def collect_functions(nodes: List[TemplateNodes]) -> None:
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
                        and re.search(r"bad|good|sink", name or "", re.IGNORECASE)
                    ):
                        functions.append(node)

                if isinstance(children, list):
                    collect_functions(children)
            else:
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
