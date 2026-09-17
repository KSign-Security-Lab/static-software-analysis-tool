import re
from typing import Any, Dict, List, Optional, Set, Tuple

from ..knowledge.c_stdlib import (
    ALLOC_CALLS_FOR_SIZEOF,
    AST_FLAG_SLOTS,
    MEM_ALLOC_FUNCS_LOWER,
    MEM_ALLOC_FUNCS_RAW,
    UNBOUNDED,
    UNBOUNDED_CALLS,
    VARARGS_CALLS,
    call_sem_cat_id_from_name,
)
from ..nodes import (
    CALL_NODE_TYPES,
    GUARD_KIND_IF,
    GUARD_KIND_LOOP,
    IF_ELSE_BRANCH,
    IF_THEN_BRANCH,
    LOOP_BODY_BRANCH,
    fullname_from_expr,
    guards_from_condition_ast,
    guards_from_for_header,
    unwrap_ast,
    unwrap_cast_typeref,
)


KEEP_TYPES = {
    "VariableDeclaration",
    "ArrayDeclaration",
    "PointerDeclaration",
    "AssignmentExpression",
    "IfStatement",
    "ForStatement",
    "WhileStatement",
    "DoWhileStatement",
    "SwitchStatement",
    "BreakStatement",
    "ContinueStatement",
    "StandardLibCall",
    "UserDefinedCall",
}

SCHEMA_VERSION = "v1.11-fd1"
NODE_TYPE_ID = {
    "FunctionEntry": 1,
    "ParameterDeclaration": 2,
    "VariableDeclaration": 3,
    "ArrayDeclaration": 4,
    "PointerDeclaration": 5,
    "AssignmentExpression": 6,
    "IfStatement": 10,
    "ForStatement": 11,
    "WhileStatement": 12,
    "DoWhileStatement": 13,
    "SwitchStatement": 14,
    "BreakStatement": 20,
    "ContinueStatement": 21,
    "StandardLibCall": 30,
    "UserDefinedCall": 31,
    "CallExpression": 32,
}

_GK = {1: 0, 2: 1, 4: 2}


CASE_LABEL_TYPES = {"CaseLabel", "DefaultLabel"}
JUMP_NODE_TYPES = {"BreakStatement", "ContinueStatement"}
JUMP_KEYWORD = {"BreakStatement": "break", "ContinueStatement": "continue"}
LOOP_NODE_TYPES = {"ForStatement", "WhileStatement", "DoWhileStatement", "DoStatement"}
DO_WHILE_NODE_TYPES = {"DoWhileStatement", "DoStatement"}
GENERIC_SKIP = {
    "IfStatement",
    "ForStatement",
    "WhileStatement",
    "DoWhileStatement",
    "SwitchStatement",
    "BreakStatement",
    "ContinueStatement",
}
CONTROL_NODES = {"IfStatement", "ForStatement", "WhileStatement", "SwitchStatement"}


def _active_guard_summary(active_guards: Dict[str, Dict[str, Any]]) -> Tuple[int, int, float]:
    return (
        1 if any(g.get("lower", 0) == 1 for g in active_guards.values()) else 0,
        1 if any(g.get("upper", 0) == 1 for g in active_guards.values()) else 0,
        max((g.get("upper_const", 0.0) for g in active_guards.values()), default=0.0),
    )


def _squeeze(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def _node_code(node: Optional[Dict[str, Any]]) -> str:
    return (node.get("code") if isinstance(node, dict) else "") or ""


def _arg_texts(code: str | None) -> List[str]:
    if not code:
        return []
    open_paren, close_paren = code.find("("), code.rfind(")")
    if open_paren == -1 or close_paren == -1 or close_paren <= open_paren:
        return []
    inner = code[open_paren + 1 : close_paren]
    return [part.strip() for part in inner.split(",")] if inner else []


def _has_sizeof_text(node: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(node, dict):
        return False
    if "sizeof(" in _node_code(node):
        return True
    if node.get("nodeType") in {"SizeOfExpression", "SizeofExpr", "SizeofExpression"}:
        return True
    return any(isinstance(c, dict) and _has_sizeof_text(c) for c in node.get("children") or [])


def _size_kind(size_node: Optional[Dict[str, Any]]) -> int:
    if not isinstance(size_node, dict):
        return 0
    text = _node_code(size_node)
    if not text:
        return 0
    if _has_sizeof_text(size_node):
        without = re.sub(r"\bsizeof\s*\([^()]*\)", "SZ", _squeeze(text))
        return 4 if re.search(r"[+\-*/]", without) else 3
    return 1 if re.fullmatch(r"\d+", _squeeze(text)) else 2


def _flag_slots(name: str, args: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    slots = AST_FLAG_SLOTS.get(name)
    if slots is None or len(args) < slots["argc"]:
        return None, None
    return args[slots["dst"]], args[slots["size"]]


LIFTABLE_SEM_CATS = {1, 2, 3, 5, 6, 7, 8}


def _node_type_id(nt: str) -> int:
    return NODE_TYPE_ID.get(nt, 0)


def _is_mem_alloc_name(fname: str) -> bool:
    f = (fname or "").strip()
    fl = f.lower()
    return (fl in MEM_ALLOC_FUNCS_LOWER) or (f in MEM_ALLOC_FUNCS_RAW)


def _node_contains_sizeof(n: Any) -> bool:
    if not isinstance(n, dict):
        return False
    code = n.get("code") or ""
    if "sizeof" in code:
        return True
    for c in n.get("children") or []:
        if _node_contains_sizeof(c):
            return True
    return False


def _strip_sizeof(s: str) -> str:
    out = []
    i = 0
    L = len(s)
    depth = 0
    in_sizeof = False
    while i < L:
        if not in_sizeof and s.startswith("sizeof", i):
            j = i + 6
            while j < L and s[j].isspace():
                j += 1
            if j < L and s[j] == "(":
                in_sizeof = True
                depth = 0
                i = j
                while i < L:
                    if s[i] == "(":
                        depth += 1
                    elif s[i] == ")":
                        depth -= 1
                        if depth == 0:
                            i += 1
                            break
                    i += 1
                continue
        out.append(s[i])
        i += 1
    return "".join(out)


def _find_matching_paren(s: str, start: int) -> int:
    depth = 0
    for i in range(start, len(s)):
        c = s[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _simple_parse_args(code: str, fname: str) -> List[str]:
    pattern = r"\b" + re.escape(fname) + r"\s*\("
    m = re.search(pattern, code or "")
    if not m:
        return []
    open_paren = m.end() - 1
    r = _find_matching_paren(code, open_paren)
    if r == -1:
        return []
    inner = code[open_paren + 1 : r]
    args: List[str] = []
    cur: List[str] = []
    depth = 0
    for ch in inner:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            args.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur:
        args.append("".join(cur).strip())
    return args


def norm_val(n: Optional[int], cap: int = 100) -> float:
    if n is None:
        return 0.0
    return min(max(int(n), 0), cap) / float(cap)


def parse_array_size_state_and_norm(code: str) -> Tuple[int, float]:
    dims = re.findall(r"\[[^\]]+\]", code or "")
    if not dims:
        return 0, 0.0
    nonconst = False
    product = 1
    evaluable = True
    for d in dims:
        expr = d.strip()[1:-1]
        expr_wo_sizeof = _strip_sizeof(expr)
        if re.search(r"[A-Za-z_]\w*", expr_wo_sizeof):
            nonconst = True
        if re.fullmatch(r"\d+", expr.strip()):
            product *= int(expr.strip())
        else:
            evaluable = False
    if nonconst:
        return 2, 0.0
    if evaluable:
        return 1, norm_val(product)
    else:
        return 1, 0.0


class ASTExtractor:
    def __init__(self, ast_json: Dict[str, Any], *, lift_pure_cond_calls: bool = False):
        self.ast = ast_json
        self.idmap: Dict[int, Dict[str, Any]] = {}
        self.parent: Dict[int, int] = {}

        def _idx(n: Any, parent_id: Optional[int] = None) -> None:
            if isinstance(n, dict):
                nid = n.get("id")
                if isinstance(nid, int):
                    self.idmap[nid] = n
                    if isinstance(parent_id, int):
                        self.parent[nid] = parent_id
                for c in n.get("children") or []:
                    _idx(c, nid)
            elif isinstance(n, list):
                for x in n:
                    _idx(x, parent_id)

        _idx(self.ast)

        self.nodes: List[Dict[str, Any]] = []
        self.id2sid: Dict[int, int] = {}

        self.edges_pc: List[Tuple[int, int, int]] = []
        self.edges_sb: List[Tuple[int, int, int]] = []
        self.edges_ast_guard: List[Dict[str, Any]] = []

        self.sid_counter = 1

        self.LIFT_PURE_COND_CALLS = lift_pure_cond_calls

        self.SWITCH_BRANCH_MODE = "int"
        self._switch_case_map: Dict[int, Dict[str, int]] = {}

        func_name = self.ast.get("name", "<func>")
        func_orig_id = self.ast.get("id") if isinstance(self.ast.get("id"), int) else None

        self.nodes.append(
            {
                "sid": 0,
                "node_type": "FunctionEntry",
                "code": f"<entry:{func_name}>",
                "orig_id": func_orig_id,
                "feat": {
                    "node_type_id": _node_type_id("FunctionEntry"),
                    "train_mask": 1,
                    "in_loop": 0,
                    "is_loop": 0,
                    "ctx_guard_strength": 0,
                    "ctx_upper_bound_norm": 0.0,
                    "is_buffer_decl": 0,
                    "buffer_size_state": 0,
                    "buffer_size_norm": 0.0,
                    "call_sem_cat_id": 0,
                    "call_flag_danger_unbounded": 0,
                    "call_flag_len_linked_to_dst": 0,
                    "call_flag_sizeof_non_dst": 0,
                    "call_flag_has_varargs": 0,
                    "call_dst_is_field": 0,
                    "call_size_kind": 0,
                    "call_len_linked_to_dst_extended": 0,
                    "call_size_is_sizeof_base_struct": 0,
                    "call_size_mismatch_field": 0,
                    "alloc_sizeof_state": 0,
                },
            }
        )

    def run(self) -> Dict[str, Any]:
        self._emit_param_statements_prologue()
        func_body = None
        for c in self.ast.get("children") or []:
            if isinstance(c, dict) and c.get("nodeType") == "CompoundStatement":
                func_body = c
                break
        if func_body is not None:
            _first, _last = self._process_block(func_body, 0, {}, 0)

        self._postprocess_control_calls()
        return {
            "nodes": self.nodes,
            "edges_ast_pc": self.edges_pc,
            "edges_ast_sb": self.edges_sb,
            "edges_ast_guard": self.edges_ast_guard,
        }

    def _link_statement(
        self, sid: int, parent_sid: int, sb_prev: Optional[int], first_sid: Optional[int]
    ) -> Tuple[int, Optional[int]]:
        self.edges_pc.append((parent_sid, sid, 0))
        if sb_prev is not None:
            self.edges_sb.append((sb_prev, sid, 1))
        return sid, (sid if first_sid is None else first_sid)

    def _link_nested(
        self,
        child_first: Optional[int],
        new_prev: Optional[int],
        sb_prev: Optional[int],
        first_sid: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        if child_first is None:
            return sb_prev, first_sid
        if sb_prev is not None:
            self.edges_sb.append((sb_prev, child_first, 1))
        return new_prev, (child_first if first_sid is None else first_sid)

    def _emit_guard_edge(self, src_sid: int, dst_sid: int, guard_kind: int, branch_label: Any) -> None:
        mode = getattr(self, "SWITCH_BRANCH_MODE", "label")
        gb = branch_label
        edge: Dict[str, Any] = {"src": src_sid, "dst": dst_sid, "edge_type": 2, "guard_kind": guard_kind}

        if guard_kind == 4 and mode == "int":
            if branch_label == "default":
                gb = -1
            else:
                try:
                    gb = self._parse_case_int(str(branch_label), src_sid)
                except Exception:
                    m = self._switch_case_fallback.setdefault(src_sid, {})
                    if branch_label not in m:
                        m[branch_label] = len(m)
                    gb = m[branch_label]
            edge["guard_branch"] = gb
            edge.setdefault("debug", {})["guard_label"] = str(branch_label)
        else:
            edge["guard_branch"] = gb

        self.edges_ast_guard.append(edge)

    def _pushed_guards(self, active: Dict[str, Dict[str, Any]], add: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        pushed = dict(active)
        for var, g in (add or {}).items():
            pushed[var] = {
                "lower": g.get("lower", 0),
                "upper": g.get("upper", 0),
                "upper_const": g.get("upper_const", 0.0),
            }
        return pushed

    def _process_loop_body(self, body: Any, loop_sid: int, pushed: Dict[str, Dict[str, Any]]) -> None:
        if not isinstance(body, dict) or body.get("nodeType") != "CompoundStatement":
            return
        body_first, _body_last = self._process_block(body, loop_sid, pushed, 1)
        if body_first is not None:
            self._emit_guard_edge(loop_sid, body_first, GUARD_KIND_LOOP, LOOP_BODY_BRANCH)

    def _handle_assignment_statement(
        self,
        ch: Dict[str, Any],
        parent_sid: int,
        active_guards: Dict[str, Dict[str, Any]],
        in_loop: int,
        sb_prev: Optional[int],
        first_sid: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        any_lower, any_upper, upper_norm = _active_guard_summary(active_guards)

        code_txt = ch.get("code", "")
        kids = ch.get("children") or []
        lhs = kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
        rhs = kids[1] if len(kids) >= 2 and isinstance(kids[1], dict) else None
        rhs_core = (
            unwrap_ast(rhs, strip_addr=False, strip_cast=True, strip_paren=True) if isinstance(rhs, dict) else None
        )
        call_node = self._find_first_call_node(rhs_core) if isinstance(rhs_core, dict) else None

        if isinstance(call_node, dict):
            node_type = call_node.get("nodeType") or "CallExpression"
            if node_type not in CALL_NODE_TYPES:
                node_type = "CallExpression"

            sid_call = self._make_node(
                node_type=node_type,
                code=call_node.get("code", ""),
                in_loop=in_loop,
                is_loop=0,
                guard_lower=any_lower,
                guard_upper=any_upper,
                upper_norm=upper_norm,
                name_hint=call_node.get("name") or "",
                orig_id=call_node.get("id"),
                debug_extra={"split_from_assign": 1},
            )
            sb_prev, first_sid = self._link_statement(sid_call, parent_sid, sb_prev, first_sid)

            sid_asg = self._make_node(
                node_type="AssignmentExpression",
                code=code_txt,
                in_loop=in_loop,
                is_loop=0,
                guard_lower=any_lower,
                guard_upper=any_upper,
                upper_norm=upper_norm,
                name_hint="",
                orig_id=ch.get("id"),
                debug_extra={"has_call_on_rhs": 1},
            )
            sb_prev, first_sid = self._link_statement(sid_asg, parent_sid, sb_prev, first_sid)
            self.nodes[-1].setdefault("debug", {})["lhs_code"] = lhs.get("code", "") if isinstance(lhs, dict) else ""
            return sb_prev, first_sid

        sid_asg = self._make_node(
            node_type="AssignmentExpression",
            code=code_txt,
            in_loop=in_loop,
            is_loop=0,
            guard_lower=any_lower,
            guard_upper=any_upper,
            upper_norm=upper_norm,
            name_hint="",
            orig_id=ch.get("id"),
        )
        return self._link_statement(sid_asg, parent_sid, sb_prev, first_sid)

    def _process_block(
        self, block_node: Dict[str, Any], parent_sid: int, active_guards: Dict[str, Dict[str, Any]], in_loop: int
    ) -> Tuple[Optional[int], Optional[int]]:
        sb_prev: Optional[int] = None
        first_sid: Optional[int] = None

        for ch in block_node.get("children") or []:
            t = ch.get("nodeType")

            if t == "CompoundStatement":
                child_first, child_last = self._process_block(ch, parent_sid, dict(active_guards), in_loop)
                sb_prev, first_sid = self._link_nested(child_first, child_last, sb_prev, first_sid)
                continue

            if t in CASE_LABEL_TYPES:
                c_first, c_last = self._process_case_block(
                    label_node=ch, switch_sid=parent_sid, active_guards=active_guards, in_loop=in_loop
                )
                sb_prev, first_sid = self._link_nested(c_first, c_last or c_first, sb_prev, first_sid)
                continue

            if t in JUMP_NODE_TYPES:
                sid_jump = self._make_node(t, JUMP_KEYWORD[t], in_loop, 0, 0, 0, 0.0, orig_id=ch.get("id"))
                sb_prev, first_sid = self._link_statement(sid_jump, parent_sid, sb_prev, first_sid)
                continue

            if t == "IfStatement":
                sb_prev, first_sid = self._handle_if(ch, parent_sid, active_guards, in_loop, sb_prev, first_sid)
                continue

            if t in LOOP_NODE_TYPES:
                sb_prev, first_sid = self._handle_loop(t, ch, parent_sid, active_guards, in_loop, sb_prev, first_sid)
                continue

            if t == "SwitchStatement":
                sb_prev, first_sid = self._handle_switch(ch, parent_sid, active_guards, in_loop, sb_prev, first_sid)
                continue

            if t == "AssignmentExpression":
                sb_prev, first_sid = self._handle_assignment_statement(
                    ch, parent_sid, active_guards, in_loop, sb_prev, first_sid
                )
                continue

            if t not in KEEP_TYPES or t in GENERIC_SKIP:
                continue
            sb_prev, first_sid = self._handle_plain_statement(
                t, ch, parent_sid, active_guards, in_loop, sb_prev, first_sid
            )

        return first_sid, sb_prev

    def _handle_if(
        self,
        ch: Dict[str, Any],
        parent_sid: int,
        active_guards: Dict[str, Dict[str, Any]],
        in_loop: int,
        sb_prev: Optional[int],
        first_sid: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        kids = ch.get("children", []) or []
        cond = kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
        then_block = kids[1] if len(kids) >= 2 and isinstance(kids[1], dict) else None
        else_block = kids[2] if len(kids) >= 3 and isinstance(kids[2], dict) else None

        if isinstance(cond, dict):
            sb_prev, _lifted_sid = self._maybe_lift_call_in_condition(
                parent_sid=parent_sid, sb_prev=sb_prev, in_loop=in_loop, cond_node=cond
            )

        cond_code = cond.get("code", "") if isinstance(cond, dict) else ch.get("code", "")
        sid_if = self._make_node("IfStatement", cond_code, in_loop, 0, 0, 0, 0.0, orig_id=ch.get("id"))
        sb_prev, first_sid = self._link_statement(sid_if, parent_sid, sb_prev, first_sid)

        cond_guards = guards_from_condition_ast(cond)
        self._guard_branch(then_block, sid_if, self._pushed_guards(active_guards, cond_guards), in_loop, IF_THEN_BRANCH)
        self._guard_branch(else_block, sid_if, dict(active_guards), in_loop, IF_ELSE_BRANCH)
        return sb_prev, first_sid

    def _guard_branch(
        self,
        block: Any,
        guard_sid: int,
        guards: Dict[str, Dict[str, Any]],
        in_loop: int,
        branch: int,
    ) -> None:
        if not isinstance(block, dict) or block.get("nodeType") != "CompoundStatement":
            return
        branch_first, _branch_last = self._process_block(block, guard_sid, guards, in_loop)
        if branch_first is not None:
            self._emit_guard_edge(guard_sid, branch_first, GUARD_KIND_IF, branch)

    def _handle_loop(
        self,
        node_type: str,
        ch: Dict[str, Any],
        parent_sid: int,
        active_guards: Dict[str, Dict[str, Any]],
        in_loop: int,
        sb_prev: Optional[int],
        first_sid: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        kids = ch.get("children") or []

        if node_type == "ForStatement":
            cond = kids[1] if len(kids) > 1 else None
            body = kids[3] if len(kids) > 3 else None
            code = ch.get("code", "")
            guards = self._for_guards(ch, cond)
        elif node_type == "WhileStatement":
            cond = kids[0] if len(kids) > 0 else None
            body = kids[1] if len(kids) > 1 else None
            code = ch.get("code", "")
            guards = guards_from_condition_ast(cond)
        else:
            body = next((k for k in kids if isinstance(k, dict) and k.get("nodeType") == "CompoundStatement"), None)
            cond = next(
                (k for k in reversed(kids) if isinstance(k, dict) and k.get("nodeType") != "CompoundStatement"),
                None,
            )
            code = cond.get("code", "") if isinstance(cond, dict) else ""
            guards = guards_from_condition_ast(cond) if code else {}

        emitted = "DoWhileStatement" if node_type in DO_WHILE_NODE_TYPES else node_type
        sid_loop = self._make_node(emitted, code, in_loop, 1, 0, 0, 0.0, orig_id=ch.get("id"))
        sb_prev, first_sid = self._link_statement(sid_loop, parent_sid, sb_prev, first_sid)
        self._process_loop_body(body, sid_loop, self._pushed_guards(active_guards, guards))
        return sb_prev, first_sid

    def _for_guards(self, for_node: Dict[str, Any], cond: Any) -> Dict[str, Any]:
        merged: Dict[str, Any] = dict(guards_from_condition_ast(cond) if isinstance(cond, dict) else {})
        for var, g in (guards_from_for_header(for_node) or {}).items():
            cur = merged.get(var, {"lower": 0, "upper": 0, "upper_const": 0.0})
            cur["lower"] = int(cur.get("lower", 0)) | int(g.get("lower", 0))
            cur["upper"] = int(cur.get("upper", 0)) | int(g.get("upper", 0))
            cur["upper_const"] = max(float(cur.get("upper_const", 0.0)), float(g.get("upper_const", 0.0)))
            merged[var] = cur
        return merged

    def _handle_switch(
        self,
        ch: Dict[str, Any],
        parent_sid: int,
        active_guards: Dict[str, Dict[str, Any]],
        in_loop: int,
        sb_prev: Optional[int],
        first_sid: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        cond_code = self._extract_switch_condition_code(ch)
        sid_sw = self._make_node("SwitchStatement", cond_code, in_loop, 0, 0, 0, 0.0, orig_id=ch.get("id"))
        sb_prev, first_sid = self._link_statement(sid_sw, parent_sid, sb_prev, first_sid)

        body = self._find_switch_body(ch)
        local_prev: Optional[int] = None
        for elem in (body.get("children") or []) if body else (ch.get("children") or []):
            if elem.get("nodeType") in CASE_LABEL_TYPES:
                c_first, c_last = self._process_case_block(elem, sid_sw, active_guards, in_loop)
            else:
                c_first, c_last = self._process_block({"children": [elem]}, sid_sw, active_guards, in_loop)
            if c_first is not None:
                if local_prev is not None:
                    self.edges_sb.append((local_prev, c_first, 1))
                local_prev = c_last or c_first
        return sb_prev, first_sid

    def _handle_plain_statement(
        self,
        node_type: str,
        ch: Dict[str, Any],
        parent_sid: int,
        active_guards: Dict[str, Dict[str, Any]],
        in_loop: int,
        sb_prev: Optional[int],
        first_sid: Optional[int],
    ) -> Tuple[Optional[int], Optional[int]]:
        name_hint = ch.get("name") or ch.get("spelling") or ""
        any_lower, any_upper, upper_norm = _active_guard_summary(active_guards)

        debug_extra = None
        if node_type == "PointerDeclaration":
            debug_extra = {
                "decl_name": ch.get("name"),
                "pointingType": ch.get("pointingType"),
                "ptr_level": ch.get("level"),
                "storage": ch.get("storage"),
            }

        sid_cur = self._make_node(
            node_type,
            ch.get("code", ""),
            in_loop,
            0,
            any_lower,
            any_upper,
            upper_norm,
            name_hint=name_hint,
            orig_id=ch.get("id"),
            debug_extra=debug_extra,
        )
        return self._link_statement(sid_cur, parent_sid, sb_prev, first_sid)

    def _postprocess_control_calls(self) -> None:
        CONTROL_NODES = {"IfStatement", "WhileStatement", "ForStatement", "DoWhileStatement", "DoStatement"}

        def _slot(fname: str, args: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
            f = (fname or "").lower()
            if f in {"memcpy", "memmove", "strncpy"} and len(args) >= 3:
                return args[0], args[2]
            if f in {"memset"} and len(args) >= 3:
                return args[0], args[2]
            if f in {"snprintf", "vsnprintf"} and len(args) >= 2:
                return args[0], args[1]
            if f in {"fgets"} and len(args) >= 2:
                return args[0], args[1]
            if f in {"read", "recv"} and len(args) >= 3:
                return args[1], args[2]
            if f in {"connect"} and len(args) >= 3:
                return args[1], args[2]
            return None, None

        for n in self.nodes:
            nt = n.get("node_type") or ""
            if nt not in CONTROL_NODES:
                continue

            orig = n.get("orig_id")
            ast_node = self.idmap.get(orig) if isinstance(orig, int) else None
            if not isinstance(ast_node, dict):
                continue

            kids = ast_node.get("children") or []
            cond = kids[0] if kids and isinstance(kids[0], dict) else None
            if not cond:
                continue

            call_node = self._find_first_call_node(cond)
            if not isinstance(call_node, dict):
                continue

            fname = call_node.get("name") or ""
            sem_id = call_sem_cat_id_from_name(fname)
            flags = self.compute_call_flags(fname=fname, call_ast=call_node, code=call_node.get("code", "")) or {}

            try:
                args = self._get_call_args_from_ast(call_node)
            except Exception:
                args = []

            dst_node, size_node = _slot(fname, args)

            if isinstance(dst_node, dict) and isinstance(size_node, dict):
                dst_core = unwrap_ast(dst_node, strip_addr=True, strip_cast=True, strip_paren=True) or dst_node
                sizeof_present = self._contains_sizeof_node(size_node)

                try:
                    dst_names = set(self._idents_from_ast_node(dst_core, skip_sizeof=True, skip_callee=True))
                except Exception:
                    dst_names = set()
                dst_full = self._fullname_from_expr(dst_core)
                if dst_full:
                    dst_names.add(dst_full)

                linked = False
                if dst_names:
                    sizeof_idents = set()

                    def _collect_sizeof_idents(node: Any) -> None:
                        if not isinstance(node, dict):
                            return
                        nt = node.get("nodeType") or ""
                        if nt in {"SizeOfExpression", "SizeOf", "TypeSizeOf", "UnarySizeOf"}:
                            targ = (node.get("children") or [None])[0]
                            code_t = self._code_of(targ)
                            if code_t:
                                sizeof_idents.add(code_t.replace(" ", ""))
                        for ch in node.get("children") or []:
                            _collect_sizeof_idents(ch)

                    _collect_sizeof_idents(size_node)

                    for dn in dst_names:
                        base = dn.split(".")[0]
                        cand = {dn, f"*{dn}", f"{dn}[0]", base}
                        if any(c.replace(" ", "") in sizeof_idents for c in cand):
                            linked = True
                            break

                if sizeof_present:
                    flags["call_flag_len_linked_to_dst"] = 1 if linked else 0
                    flags["call_flag_sizeof_non_dst"] = 0 if linked else 1

            dbg = n.setdefault("debug", {})
            dbg["cond_call"] = {
                "name": fname,
                "sem_id": int(sem_id),
                "flags": {
                    "danger_unbounded": int(flags.get("call_flag_danger_unbounded", 0)),
                    "len_linked_to_dst": int(flags.get("call_flag_len_linked_to_dst", 0)),
                    "sizeof_non_dst": int(flags.get("call_flag_sizeof_non_dst", 0)),
                    "has_varargs": int(flags.get("call_flag_has_varargs", 0)),
                    "alloc_sizeof_state": int(flags.get("alloc_sizeof_state", 0)),
                },
            }

    def _process_case_block(
        self, label_node: Dict[str, Any], switch_sid: int, active_guards: Dict[str, Dict[str, Any]], in_loop: int
    ) -> Tuple[Optional[int], Optional[int]]:
        label_str = self._normalize_case_label(label_node)
        first_sid, prev_sid = None, None

        mode = getattr(self, "SWITCH_BRANCH_MODE", "int")
        if mode not in ("label", "int"):
            mode = "int"

        for elem in label_node.get("children") or []:
            cf, cl = self._process_block({"children": [elem]}, switch_sid, active_guards, in_loop)
            if cf is None:
                continue

            if first_sid is None:
                first_sid = cf
                edge: Dict[str, Any] = {"src": switch_sid, "dst": first_sid, "edge_type": 2, "guard_kind": 4}
                if mode == "int":
                    if label_str == "default":
                        guard_branch = -1
                    else:
                        guard_branch = self._parse_case_int(label_str, switch_sid)
                    edge["guard_branch"] = guard_branch
                    edge.setdefault("debug", {})["guard_label"] = label_str
                else:
                    edge["guard_branch"] = label_str

                self.edges_ast_guard.append(edge)

            if prev_sid is not None:
                self.edges_sb.append((prev_sid, cf, 1))
            prev_sid = cl or cf

        return first_sid, prev_sid

    def _parse_case_int(self, label_str: str, switch_sid: int) -> int:
        s = (label_str or "").strip()
        try:
            if s.startswith("L'") and s.endswith("'") and len(s) >= 4:
                s = s[1:]
            if len(s) >= 3 and s[0] == "'" and s[-1] == "'":
                payload = s[1:-1]
                ch = bytes(payload, "utf-8").decode("unicode_escape")
                return ord(ch[0]) if ch else 0
            if s.lower().startswith(("+0x", "-0x", "0x")):
                return int(s, 16)
            if re.fullmatch(r"[+-]?0[0-7]+", s):
                return int(s, 8)
            return int(s, 10)
        except Exception:
            pass
        m = getattr(self, "_switch_case_fallback", None)
        if m is None:
            self._switch_case_fallback: Dict[int, Dict[Any, int]] = {}
            m = self._switch_case_fallback
        m_sw = m.setdefault(switch_sid, {})
        if s not in m_sw:
            m_sw[s] = len(m_sw)
        return int(m_sw[s])

    def _normalize_case_label(self, node: Dict[str, Any]) -> str:
        t = node.get("nodeType")
        code = (node.get("code") or "").strip()
        if t == "DefaultLabel":
            return "default"
        if code.lower().startswith("case"):
            s = code[len("case") :].strip()
            if s.endswith(":"):
                s = s[:-1].strip()
            return s or "case"
        return code or "case"

    def _find_switch_body(self, sw_node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for k in sw_node.get("children") or []:
            if isinstance(k, dict) and k.get("nodeType") in {"CompoundStatement", "BlockStatement"}:
                return k
        return None

    def _extract_switch_condition_code(self, sw_node: Dict[str, Any]) -> str:
        for k in sw_node.get("children") or []:
            if isinstance(k, dict) and k.get("nodeType") not in {
                "CompoundStatement",
                "BlockStatement",
                "CaseLabel",
                "DefaultLabel",
            }:
                return str(k.get("code", ""))
        code = str(sw_node.get("code", ""))
        try:
            open_paren = code.find("(")
            close_paren = code.find(")")
            if 0 <= open_paren < close_paren:
                return code[open_paren + 1 : close_paren]
        except Exception:
            pass
        return str(code)

    def _make_node(
        self,
        node_type: str,
        code: str,
        in_loop: int,
        is_loop: int,
        guard_lower: int,
        guard_upper: int,
        upper_norm: float,
        name_hint: str = "",
        orig_id: Optional[int] = None,
        debug_extra: Optional[Dict[str, Any]] = None,
    ) -> int:
        sid = self.sid_counter
        self.sid_counter += 1

        if node_type in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
            call_sem_cat_id = call_sem_cat_id_from_name(name_hint) if name_hint else 0
            raw_ast = self.idmap.get(orig_id) if isinstance(orig_id, int) else None
            call_ast = None
            if isinstance(raw_ast, dict) and raw_ast.get("nodeType") in {"ParameterList", "ArgumentList"}:
                call_ast = raw_ast
            elif isinstance(raw_ast, dict) and raw_ast.get("nodeType") in {
                "CallExpression",
                "StandardLibCall",
                "UserDefinedCall",
            }:
                call_ast = raw_ast
            elif isinstance(raw_ast, dict):
                call_ast = self._nearest_call_node(raw_ast)

            call_flags = self.compute_call_flags(fname=name_hint, call_ast=call_ast, code=code)

        else:
            call_sem_cat_id = 0
            call_flags = self._zero_call_flags()

        is_buf_decl = 1 if node_type == "ArrayDeclaration" else 0
        if is_buf_decl:
            buf_state, buf_norm = parse_array_size_state_and_norm(code)
        else:
            buf_state, buf_norm = (0, 0.0)

        ctx_strength = (1 if guard_lower else 0) + (2 if guard_upper else 0)
        train_mask = 1
        if node_type in {"BreakStatement", "ContinueStatement"}:
            train_mask = 0

        feat = {
            "node_type_id": _node_type_id(node_type),
            "train_mask": train_mask,
            "in_loop": in_loop,
            "is_loop": is_loop,
            "ctx_guard_strength": ctx_strength,
            "ctx_upper_bound_norm": (upper_norm if guard_upper else 0.0),
            "is_buffer_decl": is_buf_decl,
            "buffer_size_state": buf_state,
            "buffer_size_norm": buf_norm,
            "call_sem_cat_id": call_sem_cat_id,
            "call_flag_danger_unbounded": call_flags["call_flag_danger_unbounded"],
            "call_flag_len_linked_to_dst": call_flags["call_flag_len_linked_to_dst"],
            "call_flag_sizeof_non_dst": call_flags["call_flag_sizeof_non_dst"],
            "call_flag_has_varargs": call_flags["call_flag_has_varargs"],
            "call_dst_is_field": call_flags["call_dst_is_field"],
            "call_size_kind": call_flags["call_size_kind"],
            "call_len_linked_to_dst_extended": call_flags["call_len_linked_to_dst_extended"],
            "call_size_is_sizeof_base_struct": call_flags["call_size_is_sizeof_base_struct"],
            "call_size_mismatch_field": call_flags["call_size_mismatch_field"],
            "alloc_sizeof_state": call_flags["alloc_sizeof_state"],
        }

        row = {
            "sid": sid,
            "node_type": node_type,
            "code": (code or "").strip(),
            "orig_id": orig_id,
            "feat": feat,
        }
        if debug_extra:
            row["debug"] = dict(debug_extra)

        self.nodes.append(row)
        if isinstance(orig_id, int):
            self.id2sid[orig_id] = sid

        return sid

    def compute_call_flags(
        self, fname: str | None = None, call_ast: Optional[Dict[str, Any]] = None, code: str | None = None
    ) -> Dict[str, int]:
        flags = self._zero_call_flags()
        low = (fname or "").lower()

        if low in VARARGS_CALLS:
            flags["call_flag_has_varargs"] = 1
        if low in ALLOC_CALLS_FOR_SIZEOF:
            flags["alloc_sizeof_state"] = self._alloc_sizeof_state(call_ast, code)

        if not isinstance(call_ast, dict):
            if low in UNBOUNDED_CALLS:
                flags["call_flag_danger_unbounded"] = 1
            return flags

        if low in UNBOUNDED:
            flags["call_flag_danger_unbounded"] = 1

        args = self._get_call_args_from_ast(call_ast)
        dst_node, size_node = _flag_slots(low, args)

        flags["call_size_kind"] = _size_kind(size_node)

        dst_core = self._unwrap_dst(dst_node)
        base_name, field_name = self._dst_field_parts(dst_core)
        flags["call_dst_is_field"] = 1 if base_name else 0

        if isinstance(size_node, dict):
            self._apply_size_link_flags(flags, size_node, dst_core, base_name, field_name)
        return flags

    def _alloc_sizeof_state(self, call_ast: Optional[Dict[str, Any]], code: str | None) -> int:
        if isinstance(call_ast, dict):
            joined = ",".join(_node_code(k) for k in self._get_call_args_from_ast(call_ast))
        else:
            joined = ",".join(_arg_texts(code))
        return 2 if re.search(r"\bsizeof\s*\(", joined) else 1

    def _unwrap_dst(self, node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        try:
            return unwrap_ast(node, strip_addr=True, strip_cast=True, strip_paren=True)
        except Exception:
            return node

    def _dst_field_parts(self, dst_node: Optional[Dict[str, Any]]) -> Tuple[str, str]:
        if not isinstance(dst_node, dict):
            return "", ""
        full = self._fullname_from_expr(dst_node) or ""
        for separator in ("->", "."):
            if separator in full:
                base, field = full.split(separator, 1)
                return base, field
        return "", ""

    def _apply_size_link_flags(
        self,
        flags: Dict[str, int],
        size_node: Dict[str, Any],
        dst_core: Optional[Dict[str, Any]],
        base_name: str,
        field_name: str,
    ) -> None:
        size_code = _node_code(size_node)
        sizeof_present = "sizeof(" in size_code

        names = self._idents_or_empty(dst_core)
        dst_full = self._fullname_from_expr(dst_core) or ""
        if dst_full:
            names.add(dst_full)

        linked = (
            any(
                f"sizeof({name})" in size_code or f"sizeof(*{name})" in size_code or f"sizeof({name}[0])" in size_code
                for name in names
            )
            if size_code and names
            else False
        )

        linked_ext = False
        if base_name and field_name:
            base, field = re.escape(base_name), re.escape(field_name)
            if re.search(rf"\bsizeof\s*\(\s*{base}\s*\.\s*{field}\s*\)\s*", size_code):
                linked_ext = True
            if re.search(rf"\bsizeof\s*\(\s*{base}\s*\)\s*", size_code):
                flags["call_size_is_sizeof_base_struct"] = 1

        if linked or linked_ext:
            flags["call_flag_len_linked_to_dst"] = 1
        if linked_ext:
            flags["call_len_linked_to_dst_extended"] = 1
        if sizeof_present and not (linked or linked_ext):
            flags["call_flag_sizeof_non_dst"] = 1

        if base_name and (
            flags["call_size_is_sizeof_base_struct"] == 1
            or (
                sizeof_present
                and flags["call_flag_len_linked_to_dst"] == 0
                and flags["call_len_linked_to_dst_extended"] == 0
            )
        ):
            flags["call_size_mismatch_field"] = 1

    def _idents_or_empty(self, node: Optional[Dict[str, Any]]) -> Set[str]:
        try:
            return set(self._idents_from_ast_node(node, skip_sizeof=True, skip_callee=True))
        except Exception:
            return set()

    def _find_first_call_node(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(node, dict):
            return None
        nt = node.get("nodeType")
        if nt in CALL_NODE_TYPES:
            if not self._is_macro_constant_call(node):
                return node
        for ch in node.get("children") or []:
            if isinstance(ch, dict):
                f = self._find_first_call_node(ch)
                if f is not None:
                    return f
        return None

    def _nearest_call_node(self, node: Optional[Dict[str, Any]], max_hops: int = 64) -> Optional[Dict[str, Any]]:
        cur = node
        seen = set()
        hops = 0
        while isinstance(cur, dict) and cur.get("nodeType") not in CALL_NODE_TYPES:
            nid = cur.get("id")
            if not isinstance(nid, int):
                return None
            if nid in seen:
                return None
            seen.add(nid)
            pid = self.parent.get(nid)
            if not isinstance(pid, int) or pid == nid:
                return None
            cur = self.idmap.get(pid)
            hops += 1
            if hops > max_hops:
                return None
        return cur if isinstance(cur, dict) and cur.get("nodeType") in CALL_NODE_TYPES else None

    def _maybe_lift_call_in_condition(
        self, parent_sid: int, sb_prev: int | None, in_loop: int, cond_node: Dict[str, Any]
    ) -> tuple[int | None, int | None]:
        call_node = self._find_first_call_node(cond_node)
        if not isinstance(call_node, dict):
            return sb_prev, None

        if self._is_macro_constant_call(call_node):
            return sb_prev, None

        fname = call_node.get("name") or ""
        sem_id = call_sem_cat_id_from_name(fname)
        lift_ok = sem_id in LIFTABLE_SEM_CATS
        if not lift_ok and getattr(self, "LIFT_PURE_COND_CALLS", False):
            lift_ok = sem_id in {9, 10}
        if not lift_ok:
            return sb_prev, None

        ctype = call_node.get("nodeType") or "CallExpression"
        if ctype not in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
            ctype = "CallExpression"

        orig_id = call_node.get("id") if isinstance(call_node.get("id"), int) else None

        if isinstance(orig_id, int) and orig_id in getattr(self, "id2sid", {}):
            call_sid = self.id2sid[orig_id]
        else:
            call_sid = self._make_node(
                node_type=ctype,
                code=call_node.get("code", ""),
                in_loop=in_loop,
                is_loop=0,
                guard_lower=0,
                guard_upper=0,
                upper_norm=0.0,
                name_hint=fname,
                orig_id=orig_id,
                debug_extra={"lifted_from_condition": 1},
            )

        self.edges_pc.append((parent_sid, call_sid, 0))
        if sb_prev is not None:
            self.edges_sb.append((sb_prev, call_sid, 1))

        return call_sid, call_sid

    def _get_call_args_from_ast(self, node: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not isinstance(node, dict):
            return []
        nt = node.get("nodeType")
        if nt in {"ParameterList", "ArgumentList"}:
            return [c for c in (node.get("children") or []) if isinstance(c, dict)]

        kids = node.get("children") or []
        for ch in kids:
            if isinstance(ch, dict) and ch.get("nodeType") in {"ParameterList", "ArgumentList"}:
                return [c for c in (ch.get("children") or []) if isinstance(c, dict)]
        return []

    def _find_array_length_for_var(self, var_name: str) -> str | None:
        import re as _re

        if not var_name:
            return None
        stack = [self.ast]
        while stack:
            n = stack.pop()
            if not isinstance(n, dict):
                continue
            if n.get("nodeType") == "ArrayDeclaration" and n.get("name") == var_name:
                length = n.get("length")
                if isinstance(length, str) and length:
                    return length
                code = n.get("code", "") or ""
                m = _re.search(r"\[\s*(.*?)\s*\]", code)
                if m:
                    return m.group(1)
            stack.extend([c for c in (n.get("children") or []) if isinstance(c, dict)])
        return None

    def _first_stmt_sid_under(self, ast_id: int) -> int | None:
        from collections import deque

        q = deque([ast_id])
        seen = set()
        while q:
            nid = q.popleft()
            if nid in seen:
                continue
            seen.add(nid)
            sid = self.id2sid.get(nid)
            if isinstance(sid, int):
                return sid
            node = self.idmap.get(nid)
            if not isinstance(node, dict):
                continue
            for c in node.get("children") or []:
                if isinstance(c, dict):
                    child_id = c.get("id")
                    if isinstance(child_id, int):
                        q.append(child_id)
        return None

    def _zero_call_flags(self) -> Dict[str, Any]:
        return {
            "call_flag_danger_unbounded": 0,
            "call_flag_len_linked_to_dst": 0,
            "call_flag_sizeof_non_dst": 0,
            "call_flag_has_varargs": 0,
            "call_dst_is_field": 0,
            "call_size_kind": 0,
            "call_len_linked_to_dst_extended": 0,
            "call_size_is_sizeof_base_struct": 0,
            "call_size_mismatch_field": 0,
            "alloc_sizeof_state": 0,
        }

    def _is_macro_constant_call(self, node: Optional[Dict[str, Any]]) -> bool:
        if not isinstance(node, dict):
            return False
        if node.get("nodeType") not in CALL_NODE_TYPES:
            return False
        for ch in node.get("children") or []:
            if isinstance(ch, dict) and ch.get("nodeType") in {"ParameterList", "ArgumentList"}:
                for cc in ch.get("children") or []:
                    if isinstance(cc, dict) and cc.get("nodeType") == "CompoundStatement":
                        return True
        return False

    def _contains_sizeof_node(self, node: Any) -> bool:
        if not isinstance(node, dict):
            return False

        stack = [node]
        while stack:
            n = stack.pop()
            if not isinstance(n, dict):
                continue

            nt = (n.get("nodeType") or n.get("kind") or "").strip()
            op = (n.get("operator") or n.get("op") or "").strip().lower()
            name = (n.get("name") or n.get("spelling") or "").strip().lower()
            code = (n.get("code") or "").replace(" ", "")

            if nt in {"SizeOfExpression", "SizeOf", "TypeSizeOf", "UnarySizeOf"}:
                return True

            if op == "sizeof":
                return True

            if name == "sizeof":
                return True

            if "sizeof(" in code:
                return True

            for ch in n.get("children") or []:
                if isinstance(ch, dict):
                    stack.append(ch)

        return False

    def _code_of(self, node: Any, default: str = "") -> str:
        if node is None:
            return default
        if isinstance(node, str):
            return node.strip()
        if not isinstance(node, dict):
            return default

        c = node.get("code")
        if isinstance(c, str) and c.strip():
            return c.strip()

        return default

    def _idents_from_ast_node(self, n: Any, *, skip_sizeof: bool = True, skip_callee: bool = True) -> List[str]:
        import re

        out = []
        seen = set()

        def emit(name: str | None) -> None:
            if not name:
                return
            if name not in seen:
                seen.add(name)
                out.append(name)

        def is_dict(x: Any) -> bool:
            return isinstance(x, dict)

        def children(x: Any) -> List[Any]:
            result: List[Any] = (x.get("children") or []) if is_dict(x) else []
            return result

        def node_type(x: Any) -> Optional[str]:
            return x.get("nodeType") if is_dict(x) else None

        def is_sizeof_node(x: Any) -> bool:
            if not is_dict(x):
                return False
            nt = node_type(x)
            if nt in {"SizeOfExpr", "UnaryExprOrTypeTraitExpr", "UnaryExpressionOrTypeTraitExpr"}:
                return True
            code = x.get("code")
            if isinstance(code, str) and re.match(r"^\s*sizeof\s*\(", code):
                return True
            return False

        def walk(x: Any) -> None:
            if not is_dict(x):
                return

            if skip_sizeof and is_sizeof_node(x):
                return

            nt = node_type(x)

            if nt == "Identifier":
                emit(x.get("name"))
                return

            if nt == "MemberAccess":
                try:
                    full = self._fullname_from_expr(x)
                except Exception:
                    full = None
                if full:
                    emit(full)
                    return
                for c in children(x):
                    walk(c)
                return

            if nt == "ArraySubscriptExpression":
                kids = children(x)
                base = kids[0] if len(kids) > 0 else None
                idx = kids[1] if len(kids) > 1 else None
                if is_dict(base):
                    try:
                        base_full = self._fullname_from_expr(base)
                    except Exception:
                        base_full = None
                    if base_full:
                        emit(base_full)
                    else:
                        walk(base)
                if is_dict(idx):
                    walk(idx)
                return

            if nt in {"UserDefinedCall", "StandardLibCall", "CallExpression"}:
                """
                Find UserDefinedCall/StandardLibCall within cond_node of condition (If/For/While/Switch)
                and lift as a node before the condition statement.
                """
                if not skip_callee:
                    emit(x.get("name"))
                for c in children(x):
                    walk(c)
                return

            if nt in {"PointerDereference", "AddressOf", "ParenExpression", "CastExpression", "UnaryOperator"}:
                for c in children(x):
                    walk(c)
                return

            for c in children(x):
                walk(c)

        walk(n)
        return out

    def _fullname_from_expr(self, n: Any) -> Optional[str]:
        return fullname_from_expr(n, unwrap=unwrap_cast_typeref)

    def _emit_param_statements_prologue(self) -> None:
        try:
            func = self.ast
            if not isinstance(func, dict):
                return
            plist = None
            for ch in func.get("children") or []:
                if isinstance(ch, dict) and ch.get("nodeType") in {"ParameterList", "ArgumentList"}:
                    plist = ch
                    break
            if not isinstance(plist, dict):
                return

            entry_sid = 0
            prev_sid = None
            for p in plist.get("children") or []:
                if not isinstance(p, dict) or p.get("nodeType") != "ParameterDeclaration":
                    continue
                orig_id = p.get("id") if isinstance(p.get("id"), int) else None
                if isinstance(orig_id, int) and orig_id in self.id2sid:
                    continue

                name_hint = p.get("name") or ""
                code = p.get("code") or name_hint or ""
                sid = self._make_node(
                    node_type="ParameterDeclaration",
                    code=code,
                    in_loop=0,
                    is_loop=0,
                    guard_lower=0,
                    guard_upper=0,
                    upper_norm=0.0,
                    name_hint=name_hint,
                    orig_id=orig_id,
                    debug_extra={"origin": "param_prologue"},
                )
                self.edges_pc.append((entry_sid, sid, 0))
                if prev_sid is not None:
                    self.edges_sb.append((prev_sid, sid, 1))
                prev_sid = sid
        except Exception:
            return
