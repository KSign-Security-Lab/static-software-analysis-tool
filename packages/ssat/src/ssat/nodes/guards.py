from __future__ import annotations

import re
from typing import Any, Dict, Optional

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
        return "int" in t or t == ""
    return False


def int_from_node(n: Optional[Dict[str, Any]]) -> int | None:
    if not isinstance(n, dict):
        return None
    if is_int_literal(n):
        v = n.get("value")
        try:
            return int(str(v).strip())
        except Exception:
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
            e["upper_const"] = max(e["upper_const"], norm_val(k))

    def visit(n: Optional[Dict[str, Any]]) -> None:
        if not isinstance(n, dict):
            return
        nt = n.get("nodeType")
        if nt == "BinaryExpression":
            op = n.get("operator")
            ch = n.get("children") or []
            a = ch[0] if len(ch) > 0 else None
            b = ch[1] if len(ch) > 1 else None

            if op in {"&&", "and", "AND", "||", "or", "OR"}:
                visit(a)
                visit(b)
                return

            if op in {"<", "<=", ">", ">="}:
                v_left = ident_name(a)
                k_right = int_from_node(b)
                k_left = int_from_node(a)
                v_right = ident_name(b)

                if v_left:
                    if op in {">", ">="}:
                        if k_right == 0:
                            emit_lower(v_left)
                    else:
                        emit_upper(v_left, k_right)
                    return

                if v_right:
                    if op in {">", ">="}:
                        emit_upper(v_right, k_left)
                    elif k_left == 0:
                        emit_lower(v_right)
                    return

                return

        if nt in TRANSPARENT_NODE_TYPES:
            for c in n.get("children") or []:
                visit(c)
            return

        for c in n.get("children") or []:
            visit(c)

    visit(cond_ast)
    return out


def guards_from_for_header(for_ast: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Dict[str, Any]] = {}

    if not isinstance(for_ast, dict) or for_ast.get("nodeType") != "ForStatement":
        return out

    kids = for_ast.get("children") or []
    init = kids[0] if len(kids) >= 1 else None
    inc = kids[2] if len(kids) >= 3 else None
    init_var = None
    init_nonneg = False
    if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression" and init.get("operator") == "=":
        ch = init.get("children") or []
        lhs, rhs = (ch[0] if len(ch) > 0 else None), (ch[1] if len(ch) > 1 else None)
        init_var = ident_name(lhs)
        kv = int_from_literal_node(rhs)
        init_nonneg = isinstance(kv, int) and kv >= 0

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

    if init_var and inc_var and init_var == inc_var and init_nonneg and inc_nondecreasing:
        out.setdefault(init_var, _new_entry())["lower"] = 1

    return out
