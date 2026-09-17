from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

CAST_NODE_TYPES = frozenset({"CastExpression", "CStyleCastExpr"})
TYPE_CHILD_NODE_TYPES = frozenset({"TypeRef", "TypeName", "TypeSpecifier"})
PAREN_NODE_TYPES = frozenset({"ParenExpression", "ParenExpr"})


def unwrap_ast(
    node: Optional[Dict[str, Any]],
    strip_addr: bool = False,
    strip_cast: bool = True,
    strip_paren: bool = True,
) -> Optional[Dict[str, Any]]:
    n = node
    while isinstance(n, dict):
        nt = n.get("nodeType")

        if strip_cast and nt in CAST_NODE_TYPES:
            kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
            n = next((c for c in kids if c.get("nodeType") not in TYPE_CHILD_NODE_TYPES), None)
            continue

        if strip_addr and (
            nt == "AddressOfExpression" or (nt == "UnaryOperator" and n.get("operator") in {"&", "&amp;"})
        ):
            kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
            n = kids[0] if kids else None
            continue
        break
    return n


def unwrap_cast_typeref(node: Any) -> Any:
    return unwrap_ast(node, strip_cast=True)


def unwrap_cast_paren(node: Any) -> Any:
    n = node
    while isinstance(n, dict) and n.get("nodeType") in (CAST_NODE_TYPES | PAREN_NODE_TYPES):
        kids = n.get("children") or []
        n = kids[0] if kids else n
    return n


def is_member_access(n: Any) -> bool:
    return isinstance(n, dict) and n.get("nodeType") == "MemberAccess"


def member_parts(n: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    if not is_member_access(n):
        return None, None, None
    kids = n.get("children") or []
    base = kids[0] if len(kids) > 0 else None
    field = kids[1] if len(kids) > 1 else None
    base_name = base.get("name") if isinstance(base, dict) and base.get("nodeType") == "Identifier" else None
    field_name = field.get("name") if isinstance(field, dict) and field.get("nodeType") == "Identifier" else None
    full = f"{base_name}.{field_name}" if base_name and field_name else None
    return base_name, field_name, full


def fullname_from_expr(n: Any, *, unwrap: Callable[[Any], Any]) -> Optional[str]:
    if n is None:
        return None

    n = unwrap(n)

    if isinstance(n, dict) and n.get("nodeType") == "ArraySubscriptExpression":
        kids = n.get("children") or []
        n = kids[0] if kids else n
        n = unwrap(n)

    while isinstance(n, dict) and (
        n.get("nodeType") == "PointerDereference"
        or (n.get("nodeType") in {"UnaryOperator", "UnaryExpression"} and n.get("operator") in {"*", "&"})
    ):
        kids = n.get("children") or []
        n = kids[0] if kids else n
        n = unwrap(n)

    if is_member_access(n):
        return member_parts(n)[2]

    if isinstance(n, dict) and n.get("nodeType") == "Identifier":
        return n.get("name")

    return None
