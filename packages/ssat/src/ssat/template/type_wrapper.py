from ..types.cpg import TreeNode
from .config.binary_expression import BinaryExpressionBooleanMap


def binary_unary_type_wrapper(node: TreeNode) -> str:
    bool_type = BinaryExpressionBooleanMap.get(node.get("name", ""))
    if bool_type:
        return bool_type

    props = node.get("properties", {})
    type_full_name = props.get("TYPE_FULL_NAME", {})
    if isinstance(type_full_name, dict):
        inner = type_full_name.get("@value", {})
        if isinstance(inner, dict):
            raw_list = inner.get("@value", [])
            if isinstance(raw_list, list) and len(raw_list) > 0:
                return "/".join(str(x) for x in raw_list)

    children_types = [infer_type_bottom_up(child) for child in node.get("children", [])]
    unique = list(set(children_types))
    if len(unique) == 1:
        return unique[0]

    return "<unknown>"


def infer_type_bottom_up(node: TreeNode) -> str:
    children = node.get("children", [])
    if len(children) == 0:
        return "unknown"
    child_types = [infer_type_bottom_up(child) for child in children]
    unique = list(set(child_types))
    if len(unique) == 1:
        return unique[0]
    return f"({' '.join(unique)})"
