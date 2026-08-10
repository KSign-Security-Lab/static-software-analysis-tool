"""Bound evidence read off a condition or a ``for`` header.

A "guard" here is evidence that a variable was compared against a bound before
it was used: ``{"data": {"lower": 1, "upper": 1, "upper_const": 0.1}}``. The AST
extractor attaches these to guard edges; the DFG extractor attaches them to
def-use edges. Both derived them with an identical copy of this code.

These read syntax only. ``lower``/``upper`` say a comparison of that shape was
written, never that it is correct or that it dominates the use.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional

#: Nodes that wrap a subexpression without changing which variable it names.
TRANSPARENT_NODE_TYPES = frozenset(
    {
        "ParenExpression",
        "ParenthesizedExpression",
        "CStyleCastExpression",
        "CXXStaticCastExpr",
        "UnaryOperator",
        "UnaryExpression",
    }
)
INT_LITERAL_NODE_TYPES = frozenset({"Literal", "IntegerLiteral", "NumberLiteral"})
PAREN_NODE_TYPES = frozenset({"ParenExpression", "ParenthesizedExpression"})
UNARY_NODE_TYPES = frozenset({"UnaryOperator", "UnaryExpression"})


def _new_entry() -> Dict[str, Any]:
    return {"lower": 0, "upper": 0, "upper_const": 0.0}


def norm_val(k: int) -> float:
    """Normalize a bound constant to ``1/k``; ``10 -> 0.1``."""
    try:
        k = int(k)
        if k <= 0:
            return 0.0
        return 1.0 / float(k)
    except Exception:
        return 0.0


def is_int_literal(n: Any) -> bool:
    if not isinstance(n, dict):
        return False
    if n.get("nodeType") in INT_LITERAL_NODE_TYPES:
        t = (n.get("type") or "").lower()
        return "int" in t or t == ""  # some front ends leave `type` empty
    return False


def int_from_node(n: Optional[Dict[str, Any]]) -> int | None:
    """Read an integer out of a literal, a negated literal, or a parenthesized one."""
    if not isinstance(n, dict):
        return None
    if is_int_literal(n):
        v = n.get("value")
        try:
            return int(str(v).strip())
        except Exception:
            # fallback: dig it out of the code text
            m = re.search(r"-?\d+", n.get("code", ""))
            return int(m.group(0)) if m else None
    if n.get("nodeType") in UNARY_NODE_TYPES and n.get("operator") == "-":
        kids = n.get("children") or []
        val = int_from_node(kids[0] if kids else None)
        return -val if isinstance(val, int) else None
    if n.get("nodeType") in PAREN_NODE_TYPES:
        ks = n.get("children") or []
        return int_from_node(ks[0]) if ks else None
    return None


def int_from_literal_node(n: Any) -> Optional[int]:
    """Read an integer out of a literal, deliberately more strictly than
    :func:`int_from_node`.

    Used by :func:`guards_from_for_header`, which had its own copy of this. The
    two are *not* interchangeable: this one accepts a literal on ``nodeType``
    alone (no ``type`` check) but gives up if ``value`` will not parse, where
    :func:`int_from_node` requires an int-ish ``type`` and falls back to
    scraping the code text. Merging them would change what counts as a bound.
    """
    if not isinstance(n, dict):
        return None
    if n.get("nodeType") in INT_LITERAL_NODE_TYPES:
        try:
            return int(str(n.get("value")).strip())
        except TypeError, ValueError:
            return None
    if n.get("nodeType") in UNARY_NODE_TYPES and n.get("operator") == "-":
        ks = n.get("children") or []
        v = int_from_literal_node(ks[0]) if ks else None
        return -v if isinstance(v, int) else None
    if n.get("nodeType") in PAREN_NODE_TYPES:
        ks = n.get("children") or []
        return int_from_literal_node(ks[0]) if ks else None
    return None


def ident_name(n: Any) -> str | None:
    """Name an expression refers to, field-sensitively (``base.field``)."""
    if not isinstance(n, dict):
        return None
    nt = n.get("nodeType")
    if nt == "Identifier":
        nm = n.get("name")
        return nm if isinstance(nm, str) and nm else None
    if nt == "MemberAccess":
        kids = n.get("children") or []
        b = ident_name(kids[0] if len(kids) > 0 else None)
        f = ident_name(kids[1] if len(kids) > 1 else None)
        if b and f:
            return f"{b}.{f}"
        return b or f
    if nt in TRANSPARENT_NODE_TYPES:
        kids = n.get("children") or []
        return ident_name(kids[0]) if kids else None
    return None


def guards_from_condition_ast(cond_ast: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Per-variable bound evidence from a condition expression.

    Rules:

    * ``x >= 0`` / ``x > 0`` -> ``lower=1``
    * ``x <= K`` / ``x < K`` (K an int literal) -> ``upper=1``, ``upper_const=norm_val(K)``
    * ``&&`` merges both sides; ``||`` also merges both, conservatively
    * flipped comparisons (``0 < x``, ``10 > x``) are read in the right direction
    * a non-constant upper bound (``x < N``) gives ``upper=1`` but leaves
      ``upper_const`` at 0.0, there being nothing to normalize
    """
    out: Dict[str, Dict[str, Any]] = {}

    def emit_lower(var: str) -> None:
        if not var:
            return
        out.setdefault(var, _new_entry())["lower"] = 1

    def emit_upper(var: str, k: int | None) -> None:
        if not var:
            return
        e = out.setdefault(var, _new_entry())
        e["upper"] = 1
        if isinstance(k, int):
            e["upper_const"] = max(e["upper_const"], norm_val(k))  # keep the largest

    def visit(n: Optional[Dict[str, Any]]) -> None:
        if not isinstance(n, dict):
            return
        nt = n.get("nodeType")
        if nt == "BinaryExpression":
            op = n.get("operator")
            ch = n.get("children") or []
            a = ch[0] if len(ch) > 0 else None
            b = ch[1] if len(ch) > 1 else None

            # `&&` and `||` alike: reflect both sides
            if op in {"&&", "and", "AND", "||", "or", "OR"}:
                visit(a)
                visit(b)
                return

            if op in {"<", "<=", ">", ">="}:
                v_left = ident_name(a)  # var ? const
                k_right = int_from_node(b)
                k_left = int_from_node(a)  # const ? var
                v_right = ident_name(b)

                if v_left:
                    if op in {">", ">="}:
                        if k_right == 0:  # x > 0, x >= 0
                            emit_lower(v_left)
                    else:  # x < K, x <= K
                        emit_upper(v_left, k_right)
                    return

                if v_right:
                    # flipped: read the operator the other way round
                    if op in {">", ">="}:
                        emit_upper(v_right, k_left)  # K > x  =>  x < K
                    elif k_left == 0:
                        emit_lower(v_right)  # K < x => x > K, honoured only for K == 0
                    return

                return  # neither side is a variable against a constant

        if nt in TRANSPARENT_NODE_TYPES:
            for c in n.get("children") or []:
                visit(c)
            return

        # some other node (a conditional operator, say): keep descending
        for c in n.get("children") or []:
            visit(c)

    visit(cond_ast)
    return out


def guards_from_for_header(for_ast: Dict[str, Any]) -> Dict[str, Any]:
    """Lower-bound evidence from a ``for (init; cond; inc)`` header.

    Grants ``lower=1`` only when the same variable is initialised to a
    non-negative literal *and* is provably non-decreasing: ``i = K`` (K >= 0)
    with ``i++``, ``++i``, or ``i += k`` (k >= 0). The condition is not read
    here -- :func:`guards_from_condition_ast` covers that.
    """
    out: Dict[str, Dict[str, Any]] = {}

    if not isinstance(for_ast, dict) or for_ast.get("nodeType") != "ForStatement":
        return out

    kids = for_ast.get("children") or []
    init = kids[0] if len(kids) >= 1 else None
    inc = kids[2] if len(kids) >= 3 else None

    # 1) init: i = K (K >= 0)
    init_var = None
    init_nonneg = False
    if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression" and init.get("operator") == "=":
        ch = init.get("children") or []
        lhs, rhs = (ch[0] if len(ch) > 0 else None), (ch[1] if len(ch) > 1 else None)
        init_var = ident_name(lhs)
        kv = int_from_literal_node(rhs)
        init_nonneg = isinstance(kv, int) and kv >= 0

    # 2) inc: ++i / i++ / i += k (k >= 0)
    inc_var = None
    inc_nondecreasing = False
    if isinstance(inc, dict):
        nt = inc.get("nodeType")
        if nt in UNARY_NODE_TYPES and inc.get("operator") == "++":
            ks = inc.get("children") or []
            inc_var = ident_name(ks[0]) if ks else None
            inc_nondecreasing = True
        elif nt == "AssignmentExpression" and inc.get("operator") == "+=":
            ch = inc.get("children") or []
            lhs, rhs = (ch[0] if len(ch) > 0 else None), (ch[1] if len(ch) > 1 else None)
            inc_var = ident_name(lhs)
            step = int_from_literal_node(rhs)
            inc_nondecreasing = isinstance(step, int) and step >= 0

    # 3) same variable, non-negative start, non-decreasing step
    if init_var and inc_var and init_var == inc_var and init_nonneg and inc_nondecreasing:
        out.setdefault(init_var, _new_entry())["lower"] = 1

    return out
