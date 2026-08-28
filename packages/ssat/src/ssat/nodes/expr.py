"""Readers for expression shape in a Template AST node tree.

These answer "what lvalue does this expression name?" by peeling the wrappers a
C expression accumulates -- casts, parentheses, ``*``/``&``, array subscripts --
until an identifier or a member access is left.

Both extractors carried their own copy of every function here. The copies were
byte-identical except for :func:`fullname_from_expr`, which is why that one
takes its peeling strategy as an argument rather than picking one; see its
docstring.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple

#: Cast nodes, whose payload is the operand rather than the type.
CAST_NODE_TYPES = frozenset({"CastExpression", "CStyleCastExpr"})
#: Children of a cast that name the target type, not the value being cast.
TYPE_CHILD_NODE_TYPES = frozenset({"TypeRef", "TypeName", "TypeSpecifier"})
#: Parenthesis nodes. The C front end does not currently emit these.
PAREN_NODE_TYPES = frozenset({"ParenExpression", "ParenExpr"})


def unwrap_ast(
    node: Optional[Dict[str, Any]],
    strip_addr: bool = False,
    strip_cast: bool = True,
    strip_paren: bool = True,
) -> Optional[Dict[str, Any]]:
    """Peel the requested wrappers off an expression to reach its core.

    ``strip_paren`` is accepted and ignored: our AST schema has no parenthesis
    node, so there is nothing to strip. It is kept because callers pass it
    explicitly.
    """
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
    """Peel casts, skipping the child that names the type.

    The strategy :mod:`ssat.ast.extractor` uses.
    """
    return unwrap_ast(node, strip_cast=True)


def unwrap_cast_paren(node: Any) -> Any:
    """Peel cast and parenthesis wrappers, always taking the first child.

    The strategy :mod:`ssat.dfg.extractor` uses. It differs from
    :func:`unwrap_cast_typeref` in two ways: it also peels parenthesis nodes,
    and on a cast it takes ``children[0]`` blindly -- so if a front end ever
    emits the ``TypeRef`` first, this returns the type rather than the operand.
    """
    n = node
    while isinstance(n, dict) and n.get("nodeType") in (CAST_NODE_TYPES | PAREN_NODE_TYPES):
        kids = n.get("children") or []
        n = kids[0] if kids else n
    return n


def is_member_access(n: Any) -> bool:
    return isinstance(n, dict) and n.get("nodeType") == "MemberAccess"


def member_parts(n: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (base_name, field_name, full_name='base.field') for a member access node."""
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
    """Return the identifier an expression names, field-sensitively (``s.charFirst``).

    Handles PointerDereference, unary ``*``/``&``, and the base of an array
    subscript.

    ``unwrap`` is the wrapper-peeling strategy, and the two extractors do not
    agree on it -- ast passes :func:`unwrap_cast_typeref`, dfg passes
    :func:`unwrap_cast_paren`. Both copies of this function were otherwise
    identical, so the parameter keeps each caller's behaviour exactly rather
    than silently unifying them.
    """
    # 0) null/primitive guard
    if n is None:
        return None

    # 1) unwrap cast/paren first
    n = unwrap(n)

    # 2) if array subscript, resolve its base first-child
    if isinstance(n, dict) and n.get("nodeType") == "ArraySubscriptExpression":
        kids = n.get("children") or []
        n = kids[0] if kids else n
        n = unwrap(n)

    # 3) peel pointer dereference or address-of to reach the underlying lvalue
    while isinstance(n, dict) and (
        n.get("nodeType") == "PointerDereference"
        or (n.get("nodeType") in {"UnaryOperator", "UnaryExpression"} and n.get("operator") in {"*", "&"})
    ):
        kids = n.get("children") or []
        n = kids[0] if kids else n
        n = unwrap(n)

    # 4) member access wins (field-sensitivity)
    if is_member_access(n):
        return member_parts(n)[2]

    # 5) plain identifier
    if isinstance(n, dict) and n.get("nodeType") == "Identifier":
        return n.get("name")

    return None
