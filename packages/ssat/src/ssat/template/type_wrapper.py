"""Binary and unary type wrapper for type inference."""

from ..types.cpg import TreeNode
from .config.binary_expression import BinaryExpressionBooleanMap


def binary_unary_type_wrapper(node: TreeNode) -> str:
    """
    Given a TreeNode for a call/operator, pick its result type.
    1) hard-coded boolean map for known binary operators
    2) raw TYPE_FULL_NAME if present
    3) bottom-up inference from children
    4) fallback to "<unknown>"
    """
    # 1) boolean-map override
    bool_type = BinaryExpressionBooleanMap.get(node.get("name", ""))
    if bool_type:
        return bool_type

    # 2) trust TYPE_FULL_NAME shape
    props = node.get("properties", {})
    type_full_name = props.get("TYPE_FULL_NAME", {})
    if isinstance(type_full_name, dict):
        inner = type_full_name.get("@value", {})
        if isinstance(inner, dict):
            raw_list = inner.get("@value", [])
            if isinstance(raw_list, list) and len(raw_list) > 0:
                return "/".join(str(x) for x in raw_list)

    # 3) infer from children
    children_types = [infer_type_bottom_up(child) for child in node.get("children", [])]
    unique = list(set(children_types))
    if len(unique) == 1:
        return unique[0]

    # 4) give up
    return "<unknown>"


def infer_type_bottom_up(node: TreeNode) -> str:
    """Recursively infer type by merging its children's types."""
    children = node.get("children", [])
    if len(children) == 0:
        return "unknown"
    child_types = [infer_type_bottom_up(child) for child in children]
    unique = list(set(child_types))
    if len(unique) == 1:
        return unique[0]
    return f"({' '.join(unique)})"


