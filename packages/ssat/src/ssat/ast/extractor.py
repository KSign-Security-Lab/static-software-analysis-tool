import re
from typing import Any, Dict, List, Optional, Set, Tuple

# C standard-library knowledge lives in one place; see ssat.knowledge.c_stdlib.
from ..knowledge.c_stdlib import (
    MEM_ALLOC_FUNCS_LOWER,
    MEM_ALLOC_FUNCS_RAW,
    UNBOUNDED_CALLS,
    call_sem_cat_id_from_name,
)

# ----------------------------
# Modifications
# Added DoWhileStatement, SwitchStatement
# Added BreakStatement, ContinueStatement - for order/debug (excluded from training)
# Distinguish between training and debug in flattening results
# ----------------------------

# Node types to keep (statement level)
KEEP_TYPES = {
    "VariableDeclaration",
    "ArrayDeclaration",
    "PointerDeclaration",
    "AssignmentExpression",
    "IfStatement",
    "ForStatement",
    "WhileStatement",
    "DoWhileStatement",
    "SwitchStatement",  # code = condition only
    "BreakStatement",  # for order/debug (excluded from training)
    "ContinueStatement",  # for order/debug (excluded from training)
    "StandardLibCall",
    "UserDefinedCall",
}

SCHEMA_VERSION = "v1.11-fd1"
# node type -> id (integer id for training; expand as needed)
NODE_TYPE_ID = {
    "FunctionEntry": 1,  # <- lowest level base type
    "ParameterDeclaration": 2,
    "VariableDeclaration": 3,
    "ArrayDeclaration": 4,
    "PointerDeclaration": 5,
    "AssignmentExpression": 6,
    # control flow blocks maintain original range
    "IfStatement": 10,
    "ForStatement": 11,
    "WhileStatement": 12,
    "DoWhileStatement": 13,
    "SwitchStatement": 14,
    # order/debug only
    "BreakStatement": 20,
    "ContinueStatement": 21,
    # call types
    "StandardLibCall": 30,
    "UserDefinedCall": 31,
    "CallExpression": 32,
    # FunctionExit reserved if used
    # "FunctionExit": 6,
}

# guard kind → onehot index (if, loop, switch)
_GK = {1: 0, 2: 1, 4: 2}


CASE_LABEL_TYPES = {"CaseLabel", "DefaultLabel"}
CONTROL_NODES = {"IfStatement", "ForStatement", "WhileStatement", "SwitchStatement"}
CALL_NODE_TYPES = {"CallExpression", "StandardLibCall", "UserDefinedCall"}

# Target categories for lifting calls
# 1:mem_alloc, 2:mem_copy, 3:ext_input, 5:mem_set, 6:net_connect, 7:net_close, 8:socket_create
LIFTABLE_SEM_CATS = {1, 2, 3, 5, 6, 7, 8}


def _node_type_id(nt: str) -> int:
    return NODE_TYPE_ID.get(nt, 0)


def _is_mem_alloc_name(fname: str) -> bool:
    f = (fname or "").strip()
    fl = f.lower()
    return (fl in MEM_ALLOC_FUNCS_LOWER) or (f in MEM_ALLOC_FUNCS_RAW)


def _node_contains_sizeof(n: Any) -> bool:
    """Conservatively detect sizeof usage within AST node tree."""
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
    """Remove sizeof(...) blocks from string to reduce false identifier detection."""
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
                # skip balanced parentheses
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
    """Returns the index of ')' corresponding to '(' at start position in string s (-1 if none)."""
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
    """Best-effort parsing of first call arguments of fname(...) in code."""
    pattern = r"\b" + re.escape(fname) + r"\s*\("
    m = re.search(pattern, code or "")
    if not m:
        return []
    open_paren = m.end() - 1
    r = _find_matching_paren(code, open_paren)
    if r == -1:
        return []
    inner = code[open_paren + 1 : r]
    # split by top-level commas
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
    """Normalize 0..cap to 0..1. 0.0 for None/negative."""
    if n is None:
        return 0.0
    return min(max(int(n), 0), cap) / float(cap)


def parse_array_size_state_and_norm(code: str) -> Tuple[int, float]:
    """
    Calculate (buffer_size_state, buffer_size_norm) from array declaration string.
      - state: 0=NA (not an array), 1=CONST, 2=NONCONST
      - norm : normalized value for CONST, else 0.0
    """
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
    # CONST
    if evaluable:
        return 1, norm_val(product)
    else:
        return 1, 0.0


class ASTExtractor:
    def __init__(self, ast_json: Dict[str, Any], *, lift_pure_cond_calls: bool = False):

        self.ast = ast_json
        # id -> AST node map for quick lookup
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
        self.id2sid: Dict[int, int] = {}  # AST orig_id -> created sid (prevent duplicates)

        self.edges_pc: List[Tuple[int, int, int]] = []  # (src, dst, 0)
        self.edges_sb: List[Tuple[int, int, int]] = []  # (src, dst, 1)
        # GUARD edges use guard_kind in training, guard_branch is for debug only
        self.edges_ast_guard: List[Dict[str, Any]] = []  # {"src","dst","edge_type":2,"guard_kind", "guard_branch"(dbg)}

        self.sid_counter = 1

        self.LIFT_PURE_COND_CALLS = lift_pure_cond_calls

        # Switch branch representation mode: "label" | "numeric"
        self.SWITCH_BRANCH_MODE = "int"  # Changed default to "int" (label preserved only for debug)
        self._switch_case_map: Dict[int, Dict[str, int]] = {}

        func_name = self.ast.get("name", "<func>")
        func_orig_id = self.ast.get("id") if isinstance(self.ast.get("id"), int) else None

        self.nodes.append(
            {
                "sid": 0,
                "node_type": "FunctionEntry",
                "code": f"<entry:{func_name}>",
                "orig_id": func_orig_id,
                # Training feat (AST-GNN specific features only)
                "feat": {
                    "node_type_id": _node_type_id("FunctionEntry"),  # <- integer ID (FunctionEntry=1)
                    "train_mask": 1,
                    "in_loop": 0,
                    "is_loop": 0,
                    "ctx_guard_strength": 0,
                    "ctx_upper_bound_norm": 0.0,
                    "is_buffer_decl": 0,
                    "buffer_size_state": 0,
                    "buffer_size_norm": 0.0,
                    "call_sem_cat_id": 0,
                    # AST enhancement flags for call/size (0 as it is non-call)
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
                # debug attached only when additional notes are present (no duplication)
            }
        )

    def run(self) -> Dict[str, Any]:
        """Flatten the function body into statement-level nodes and edges."""
        # Emit ParameterDeclaration as prologue before walking the body.
        self._emit_param_statements_prologue()
        func_body = None
        for c in self.ast.get("children") or []:
            if isinstance(c, dict) and c.get("nodeType") == "CompoundStatement":
                func_body = c
                break
        if func_body is not None:
            _first, _last = self._process_block(func_body, 0, {}, 0)

        # postprocess control nodes for call semantics
        self._postprocess_control_calls()
        return {
            "nodes": self.nodes,  # Nodes: {sid, node_type_id, code, orig_id, feat{...}, debug{...}}
            "edges_ast_pc": self.edges_pc,  # (Unchanged) [(parent_sid, child_sid, 0)]
            "edges_ast_sb": self.edges_sb,  # (Unchanged) [(prev_sid, next_sid, 1)]
            "edges_ast_guard": self.edges_ast_guard,  # (Unchanged) [{src, dst, guard_kind, guard_branch}]
        }

    def _process_block(
        self, block_node: Dict[str, Any], parent_sid: int, active_guards: Dict[str, Dict[str, Any]], in_loop: int
    ) -> Tuple[Optional[int], Optional[int]]:
        """
        Traverse block (CompoundStatement) and create statement-level nodes
        - edges_ast_pc: parent->child
        - edges_ast_sb: statement order
        - edges_ast_guard: (guard_stmt -> first_stmt_in_block, {guard_kind, guard_branch})
        # (Modified) train_mask: Break/Continue excluded from training data (0)
        # Note: _make_node handles train_mask setting, removed redundant code overwrite.
        # Switch flattening: external SB always continues from switch node (sb_prev = sid_sw fixed).
        # edges_ast_guard generated via common helper (_emit_guard) -> training uses kind, debug keeps guard_branch label.
        # If/For/While/DoWhile guard edges use _emit_guard.
        # Removed unnecessary gfeat calculation (aggregation happens in DFG phase).
        """

        # --- guard edge emitter (maintain labels for debug, use kind only for training) ---
        def _emit_guard(src_sid: int, dst_sid: int, guard_kind: int, branch_label: Any) -> None:
            """
            branch_label:
            if → 0(then) / 1(else)
            loop → 2
            switch → label string like "7", "default"
            """
            mode = getattr(self, "SWITCH_BRANCH_MODE", "label")  # "label" | "numeric"
            gb = branch_label

            edge: Dict[str, Any] = {"src": src_sid, "dst": dst_sid, "edge_type": 2, "guard_kind": guard_kind}

            if guard_kind == 4 and mode == "int":
                # Only switch uses integer encoding + preserves debug label
                if branch_label == "default":
                    gb = -1
                else:
                    # Parse as integer if possible, else per-switch stable mapping
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
                # if/loop or switch in label mode
                edge["guard_branch"] = gb
                # edge["guard_branch_dbg"] not added (deduplication)

            self.edges_ast_guard.append(edge)

        sb_prev: Optional[int] = None
        first_sid: Optional[int] = None

        for ch in block_node.get("children") or []:
            t = ch.get("nodeType")

            # Nested block
            if t == "CompoundStatement":
                child_first, child_last = self._process_block(ch, parent_sid, dict(active_guards), in_loop)
                if child_first is not None:
                    if sb_prev is not None:
                        self.edges_sb.append((sb_prev, child_first, 1))
                    if first_sid is None:
                        first_sid = child_first
                    sb_prev = child_last
                continue

            # ContinueStatement: control transfer only (no DFG, excluded from training)
            if t == "ContinueStatement":
                sid_ct = self._make_node("ContinueStatement", "continue", in_loop, 0, 0, 0, 0.0, orig_id=ch.get("id"))
                self.edges_pc.append((parent_sid, sid_ct, 0))
                if sb_prev is not None:
                    self.edges_sb.append((sb_prev, sid_ct, 1))
                if first_sid is None:
                    first_sid = sid_ct
                sb_prev = sid_ct
                continue

            # ------------------------------------------------------------
            # CaseLabel / DefaultLabel (switch internal container only)
            # - Label itself is not made into a Statement
            # - Flatten internal child Statements and give first Statement
            #   guard(kind=4, branch=label)
            # - Connect with SB/PC up to the last child (e.g., break;)
            # ------------------------------------------------------------
            if t in CASE_LABEL_TYPES:
                c_first, c_last = self._process_case_block(
                    label_node=ch, switch_sid=parent_sid, active_guards=active_guards, in_loop=in_loop
                )
                if c_first is not None:
                    if sb_prev is not None:
                        self.edges_sb.append((sb_prev, c_first, 1))
                    if first_sid is None:
                        first_sid = c_first
                    sb_prev = c_last or c_first
                continue

            # BreakStatement: control transfer only (no DFG)
            if t == "BreakStatement":
                sid_br = self._make_node("BreakStatement", "break", in_loop, 0, 0, 0, 0.0, orig_id=ch.get("id"))
                self.edges_pc.append((parent_sid, sid_br, 0))
                if sb_prev is not None:
                    self.edges_sb.append((sb_prev, sid_br, 1))
                if first_sid is None:
                    first_sid = sid_br
                sb_prev = sid_br
                continue

            if t == "IfStatement":
                kids = ch.get("children", []) or []
                cond = kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
                then_block = kids[1] if len(kids) >= 2 and isinstance(kids[1], dict) else None
                else_block = kids[2] if len(kids) >= 3 and isinstance(kids[2], dict) else None

                # 1) (New) Lift call side effects in condition: insert 'Call Statement' before If
                if isinstance(cond, dict):
                    sb_prev, _lifted_sid = self._maybe_lift_call_in_condition(
                        parent_sid=parent_sid, sb_prev=sb_prev, in_loop=in_loop, cond_node=cond
                    )

                # 2) Create IfStatement node (condition 'code' only)
                cond_code = cond.get("code", "") if isinstance(cond, dict) else ch.get("code", "")
                sid_if = self._make_node("IfStatement", cond_code, in_loop, 0, 0, 0, 0.0, orig_id=ch.get("id"))
                self.edges_pc.append((parent_sid, sid_if, 0))
                if sb_prev is not None:
                    self.edges_sb.append((sb_prev, sid_if, 1))
                if first_sid is None:
                    first_sid = sid_if
                sb_prev = sid_if

                # 3) Aggregate guard context
                cond_guards = self._guards_from_condition_ast(cond)

                def _push_guards(base: Dict[str, Any], add: Dict[str, Any]) -> Dict[str, Any]:
                    pushed = dict(base)
                    for v, g in (add or {}).items():
                        pushed[v] = {
                            "lower": g.get("lower", 0),
                            "upper": g.get("upper", 0),
                            "upper_const": g.get("upper_const", 0.0),
                        }
                    return pushed

                # 4) THEN
                if isinstance(then_block, dict) and then_block.get("nodeType") == "CompoundStatement":
                    then_first, _then_last = self._process_block(
                        then_block, sid_if, _push_guards(active_guards, cond_guards), in_loop
                    )
                    if then_first is not None:
                        _emit_guard(sid_if, then_first, 1, 0)  # then=0

                # 5) ELSE
                if isinstance(else_block, dict) and else_block.get("nodeType") == "CompoundStatement":
                    else_first, _else_last = self._process_block(
                        else_block,
                        sid_if,
                        dict(active_guards),  # maintain context without inversion
                        in_loop,
                    )
                    if else_first is not None:
                        _emit_guard(sid_if, else_first, 1, 1)  # else=1
                continue

            # if t == "ForStatement":
            #     sid_for = self._make_node("ForStatement", ch.get("code",""), in_loop, 1, 0, 0, 0.0,
            #                             orig_id=ch.get("id"))
            #     self.edges_pc.append((parent_sid, sid_for, 0))
            # SB update: lifted node becomes the new prev
            # if sb_prev is not None:
            #         self.edges_sb.append((sb_prev, sid_for, 1))
            #     if first_sid is None:
            #         first_sid = sid_for
            #     sb_prev = sid_for

            if t == "ForStatement":
                # Create loop node
                sid_for = self._make_node(
                    "ForStatement", ch.get("code", ""), in_loop, 1, 0, 0, 0.0, orig_id=ch.get("id")
                )
                self.edges_pc.append((parent_sid, sid_for, 0))
                if sb_prev is not None:
                    self.edges_sb.append((sb_prev, sid_for, 1))
                if first_sid is None:
                    first_sid = sid_for
                sb_prev = sid_for

                kids = ch.get("children", []) or []
                cond_ast = kids[1] if len(kids) > 1 else None

                # Parse condition (AST) and also infer lower-bound from init/inc header
                guards_cond = self._guards_from_condition_ast(cond_ast) if isinstance(cond_ast, dict) else {}
                guards_hdr = self._guards_from_for_header(ch) or {}

                # Merge guards: OR for lower/upper, max for upper_const
                lguards = dict(guards_cond)
                for v, g in guards_hdr.items():
                    cur = lguards.get(v, {"lower": 0, "upper": 0, "upper_const": 0.0})
                    cur["lower"] = int(cur.get("lower", 0)) | int(g.get("lower", 0))
                    cur["upper"] = int(cur.get("upper", 0)) | int(g.get("upper", 0))
                    cur["upper_const"] = max(float(cur.get("upper_const", 0.0)), float(g.get("upper_const", 0.0)))
                    lguards[v] = cur

                pushed = dict(active_guards)
                for v, g in (lguards or {}).items():
                    pushed[v] = {
                        "lower": g.get("lower", 0),
                        "upper": g.get("upper", 0),
                        "upper_const": g.get("upper_const", 0.0),
                    }

                body = kids[3] if len(kids) > 3 else None
                if isinstance(body, dict) and body.get("nodeType") == "CompoundStatement":
                    body_first, _body_last = self._process_block(body, sid_for, pushed, 1)
                    if body_first is not None:
                        _emit_guard(sid_for, body_first, 2, 2)  # loop-body=2
                continue

            # WhileStatement
            if t == "WhileStatement":
                sid_while = self._make_node(
                    "WhileStatement", ch.get("code", ""), in_loop, 1, 0, 0, 0.0, orig_id=ch.get("id")
                )
                self.edges_pc.append((parent_sid, sid_while, 0))
                if sb_prev is not None:
                    self.edges_sb.append((sb_prev, sid_while, 1))
                if first_sid is None:
                    first_sid = sid_while
                sb_prev = sid_while

                kids = ch.get("children", []) or []
                cond = kids[0] if len(kids) > 0 else None
                # cond_code = cond.get("code","") if isinstance(cond, dict) else ""
                lguards = self._guards_from_condition_ast(cond)

                pushed = dict(active_guards)
                for v, g in lguards.items():
                    pushed[v] = {
                        "lower": g.get("lower", 0),
                        "upper": g.get("upper", 0),
                        "upper_const": g.get("upper_const", 0.0),
                    }

                body = kids[1] if len(kids) > 1 else None
                if isinstance(body, dict) and body.get("nodeType") == "CompoundStatement":
                    body_first, _ = self._process_block(body, sid_while, pushed, 1)
                    if body_first is not None:
                        _emit_guard(sid_while, body_first, 2, 2)  # loop-body=2
                continue

            # Create DoWhileStatement node (code: cond)
            if t in {"DoWhileStatement", "DoStatement"}:
                kids = ch.get("children") or []
                # body: first CompoundStatement, cond: last non-CompoundStatement
                body = next((k for k in kids if isinstance(k, dict) and k.get("nodeType") == "CompoundStatement"), None)
                cond = next(
                    (k for k in reversed(kids) if isinstance(k, dict) and k.get("nodeType") != "CompoundStatement"),
                    None,
                )
                cond_code = cond.get("code", "") if isinstance(cond, dict) else ""

                sid_do = self._make_node("DoWhileStatement", cond_code, in_loop, 1, 0, 0, 0.0, orig_id=ch.get("id"))
                self.edges_pc.append((parent_sid, sid_do, 0))
                if sb_prev is not None:
                    self.edges_sb.append((sb_prev, sid_do, 1))
                if first_sid is None:
                    first_sid = sid_do
                sb_prev = sid_do

                # build context for guard (loop) evidence injection
                lguards = self._guards_from_condition_ast(cond) if cond_code else {}
                pushed = dict(active_guards)
                for v, g in lguards.items():
                    pushed[v] = {
                        "lower": g.get("lower", 0),
                        "upper": g.get("upper", 0),
                        "upper_const": g.get("upper_const", 0.0),
                    }

                # block flattening + loop guard edge creation
                if isinstance(body, dict) and body.get("nodeType") == "CompoundStatement":
                    body_first, _ = self._process_block(body, sid_do, pushed, 1)
                    if body_first is not None:
                        _emit_guard(sid_do, body_first, 2, 2)  # loop=2

                continue

            # SwitchStatement (node creation + case/default guard edge creation)
            if t == "SwitchStatement":
                cond_code = self._extract_switch_condition_code(ch)
                sid_sw = self._make_node("SwitchStatement", cond_code, in_loop, 0, 0, 0, 0.0, orig_id=ch.get("id"))
                self.edges_pc.append((parent_sid, sid_sw, 0))
                if sb_prev is not None:
                    self.edges_sb.append((sb_prev, sid_sw, 1))
                if first_sid is None:
                    first_sid = sid_sw

                # direct traversal of CaseLabel/DefaultLabel in body
                body = self._find_switch_body(ch)
                local_prev = None
                for elem in (body.get("children") or []) if body else (ch.get("children") or []):
                    et = elem.get("nodeType")
                    if et in CASE_LABEL_TYPES:
                        c_first, c_last = self._process_case_block(elem, sid_sw, active_guards, in_loop)
                        if c_first is not None:
                            if local_prev is not None:
                                self.edges_sb.append((local_prev, c_first, 1))
                            local_prev = c_last or c_first
                    else:
                        cf, cl = self._process_block({"children": [elem]}, sid_sw, active_guards, in_loop)
                        if cf is not None:
                            if local_prev is not None:
                                self.edges_sb.append((local_prev, cf, 1))
                            local_prev = cl or cf

                # external SB always continues from switch itself to the next statement
                sb_prev = sid_sw
                continue

            # 표준/사용자 정의 호출 노드 직접 처리
            if t in {"StandardLibCall", "UserDefinedCall"}:
                call_name = ch.get("name") or ""
                code = ch.get("code", "")
                any_lower = 1 if any(g.get("lower", 0) == 1 for g in active_guards.values()) else 0
                any_upper = 1 if any(g.get("upper", 0) == 1 for g in active_guards.values()) else 0
                upper_norm = max((g.get("upper_const", 0.0) for g in active_guards.values()), default=0.0)

                sid_cur = self._make_node(
                    t, code, in_loop, 0, any_lower, any_upper, upper_norm, name_hint=call_name, orig_id=ch.get("id")
                )
                self.edges_pc.append((parent_sid, sid_cur, 0))
                if sb_prev is not None:
                    self.edges_sb.append((sb_prev, sid_cur, 1))
                if first_sid is None:
                    first_sid = sid_cur
                sb_prev = sid_cur
                continue

            # AssignmentExpression RHS에 메모리 할당 호출이 있으면 AST-GNN 피처 보정 ----
            # target 예: data = (int*)ALLOCA(10), data = malloc(n), data = calloc(k, sizeof(int))
            if t == "AssignmentExpression":
                # 컨텍스트 가드 집계
                any_lower = 1 if any(g.get("lower", 0) == 1 for g in active_guards.values()) else 0
                any_upper = 1 if any(g.get("upper", 0) == 1 for g in active_guards.values()) else 0
                upper_norm = max((g.get("upper_const", 0.0) for g in active_guards.values()), default=0.0)

                code_txt = ch.get("code", "")
                kids = ch.get("children") or []
                lhs = kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
                rhs = kids[1] if len(kids) >= 2 and isinstance(kids[1], dict) else None

                # RHS에서 첫 호출 탐색 (캐스트/괄호 벗겨 핵심만 검사)
                rhs_core = (
                    self._unwrap_ast(rhs, strip_addr=False, strip_cast=True, strip_paren=True)
                    if isinstance(rhs, dict)
                    else None
                )
                calln = self._find_first_call_node(rhs_core) if isinstance(rhs_core, dict) else None

                # 1) 호출이 있으면: 호출 노드를 먼저 "문장"으로 만든다
                if isinstance(calln, dict):
                    fname = calln.get("name") or ""
                    ctype = calln.get("nodeType") or "CallExpression"
                    if ctype not in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
                        ctype = "CallExpression"

                    # 호출 노드 생성 (is_loop=0)

                    sid_call = self._make_node(
                        node_type=ctype,
                        code=calln.get("code", ""),
                        in_loop=in_loop,
                        is_loop=0,
                        guard_lower=any_lower,
                        guard_upper=any_upper,
                        upper_norm=upper_norm,
                        name_hint=fname,
                        orig_id=calln.get("id"),
                        debug_extra={"split_from_assign": 1},
                    )
                    # PC / SB 연결
                    self.edges_pc.append((parent_sid, sid_call, 0))
                    if sb_prev is not None:
                        self.edges_sb.append((sb_prev, sid_call, 1))
                    if first_sid is None:
                        first_sid = sid_call
                    sb_prev = sid_call

                    # 2) 대입식 노드 생성 (호출 뒤에 온다; call_* 피처는 0 유지)
                    # debug: assignment after call split
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
                    self.edges_pc.append((parent_sid, sid_asg, 0))
                    if sb_prev is not None:
                        self.edges_sb.append((sb_prev, sid_asg, 1))
                    if first_sid is None:
                        first_sid = sid_asg
                    sb_prev = sid_asg

                    # (선택) 디버그 힌트: LHS/RHS 요약
                    try:
                        self.nodes[-1].setdefault("debug", {})["lhs_code"] = (
                            lhs.get("code", "") if isinstance(lhs, dict) else ""
                        )
                    except Exception:
                        pass

                    continue  # AssignmentExpression 처리 끝

                # ---- 호출이 없으면: 기존처럼 대입 노드만 생성 ----
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
                self.edges_pc.append((parent_sid, sid_asg, 0))
                if sb_prev is not None:
                    self.edges_sb.append((sb_prev, sid_asg, 1))
                if first_sid is None:
                    first_sid = sid_asg
                sb_prev = sid_asg
                continue  # ← 제너릭 분기 건너뜀 (중복 방지

            # =======================
            # 제너릭 fallback (AssignmentExpression 포함 X)
            # =======================

            # statement-level 노드만 유지 (전용 핸들러가 있는 타입은 제너릭에서 스킵)
            GENERIC_SKIP = {
                "IfStatement",
                "ForStatement",
                "WhileStatement",
                "DoWhileStatement",
                "SwitchStatement",
                "BreakStatement",
                "ContinueStatement",
            }
            if t not in KEEP_TYPES or t in GENERIC_SKIP:
                continue

            code = ch.get("code", "")
            any_lower = 1 if any(g.get("lower", 0) == 1 for g in active_guards.values()) else 0
            any_upper = 1 if any(g.get("upper", 0) == 1 for g in active_guards.values()) else 0
            upper_norm = max((g.get("upper_const", 0.0) for g in active_guards.values()), default=0.0)

            debug_extra = None
            if t == "PointerDeclaration":
                debug_extra = {
                    "decl_name": ch.get("name"),
                    "pointingType": ch.get("pointingType"),
                    "ptr_level": ch.get("level"),
                    "storage": ch.get("storage"),
                }

            name_hint = ch.get("name", "") or ch.get("spelling", "") or ""
            sid_cur = self._make_node(
                t,
                code,
                in_loop,
                0,
                any_lower,
                any_upper,
                upper_norm,
                name_hint=name_hint,
                orig_id=ch.get("id"),
                debug_extra=debug_extra,
            )

            self.edges_pc.append((parent_sid, sid_cur, 0))
            if sb_prev is not None:
                self.edges_sb.append((sb_prev, sid_cur, 1))
            if first_sid is None:
                first_sid = sid_cur
            sb_prev = sid_cur

        return first_sid, sb_prev

    def _postprocess_control_calls(self) -> None:
        """
        For control statements (If/While/For/Do*), inspect a call inside the condition.
        - v1.11: 컨트롤 노드의 학습 feat는 중립 유지(수정 금지).
        - 조건식 내 호출의 sem/flags는 debug에만 기록한다.
        """
        CONTROL_NODES = {"IfStatement", "WhileStatement", "ForStatement", "DoWhileStatement", "DoStatement"}

        # API별 dst/size 슬롯 정의(필요 최소)
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
                return args[1], args[2]  # addr, addrlen (len-linked 의미는 약함)
            return None, None

        for n in self.nodes:
            nt = n.get("node_type") or ""
            if nt not in CONTROL_NODES:
                continue

            orig = n.get("orig_id")
            ast_node = self.idmap.get(orig) if isinstance(orig, int) else None
            if not isinstance(ast_node, dict):
                continue

            # 조건식 노드(보통 첫 child)
            kids = ast_node.get("children") or []
            cond = kids[0] if kids and isinstance(kids[0], dict) else None
            if not cond:
                continue

            call_node = self._find_first_call_node(cond)
            if not isinstance(call_node, dict):
                continue

            fname = call_node.get("name") or ""
            sem_id = call_sem_cat_id_from_name(fname)

            # 기본 플래그(문자열/휴리스틱 기반) 산출
            flags = self.compute_call_flags(fname=fname, call_ast=call_node, code=call_node.get("code", "")) or {}

            # --- AST 기반 정밀 보정 (디버그용) ---
            try:
                args = self._get_call_args_from_ast(call_node)
            except Exception:
                args = []

            dst_node, size_node = _slot(fname, args)

            if isinstance(dst_node, dict) and isinstance(size_node, dict):
                # & / () / cast 를 옵션대로 제거하여 '실제 dst' 추출
                dst_core = self._unwrap_ast(dst_node, strip_addr=True, strip_cast=True, strip_paren=True) or dst_node

                # 매크로/중첩에서도 동작하도록 AST 재귀로 sizeof 존재 여부 판정
                sizeof_present = self._contains_sizeof_node(size_node)

                # dst 후보명(식별자/필드 풀네임) 수집
                try:
                    dst_names = set(self._idents_from_ast_node(dst_core, skip_sizeof=True, skip_callee=True))
                except Exception:
                    dst_names = set()
                dst_full = self._fullname_from_expr(dst_core)
                if dst_full:
                    dst_names.add(dst_full)

                # dst 연계 여부도 AST에서 sizeof의 피연산자 심볼을 수집해 비교
                linked = False
                if dst_names:
                    sizeof_idents = set()

                    def _collect_sizeof_idents(node: Any) -> None:
                        if not isinstance(node, dict):
                            return
                        nt = node.get("nodeType") or ""
                        if nt in {"SizeOfExpression", "SizeOf", "TypeSizeOf", "UnarySizeOf"}:
                            # 피연산(타입/식) 코드 추출
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

                # 보정: sizeof가 있고 dst와 연계되면 len_linked=1, 아니면 sizeof_non_dst=1
                if sizeof_present:
                    flags["call_flag_len_linked_to_dst"] = 1 if linked else 0
                    flags["call_flag_sizeof_non_dst"] = 0 if linked else 1

            # --- debug에만 남김 ---
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
            # feat는 수정하지 않음

    def _process_case_block(
        self, label_node: Dict[str, Any], switch_sid: int, active_guards: Dict[str, Dict[str, Any]], in_loop: int
    ) -> Tuple[Optional[int], Optional[int]]:
        """CaseLabel/DefaultLabel 컨테이너의 자식 Statement들을 평탄화하고
        첫 Statement에 switch-guard를 부여한다.
        - guard_branch: 정수 인코딩(기본). default=-1, 그 외 case는 '상수 표현'을 정수로 파싱
        - debug.guard_label: 원래 라벨 문자열 보존"""

        label_str = self._normalize_case_label(label_node)
        first_sid, prev_sid = None, None

        # 모드: "label"(레거시) | "int"(스펙 권장, 기본)
        mode = getattr(self, "SWITCH_BRANCH_MODE", "int")  # "label" | "int"
        if mode not in ("label", "int"):
            mode = "int"

        for elem in label_node.get("children") or []:
            # 자식 하나를 Statement처럼 처리 (parent = switch_sid)
            cf, cl = self._process_block({"children": [elem]}, switch_sid, active_guards, in_loop)
            if cf is None:
                continue

            # 첫 Statement면 guard(edge) 부여
            if first_sid is None:
                first_sid = cf
                edge: Dict[str, Any] = {"src": switch_sid, "dst": first_sid, "edge_type": 2, "guard_kind": 4}
                if mode == "int":
                    # default:-1, 그 외 case는 상수 표현을 정수로 파싱
                    if label_str == "default":
                        guard_branch = -1
                    else:
                        guard_branch = self._parse_case_int(label_str, switch_sid)
                    edge["guard_branch"] = guard_branch
                    edge.setdefault("debug", {})["guard_label"] = label_str
                else:
                    # 라벨 문자열 그대로(디버그 가독성)
                    edge["guard_branch"] = label_str

                self.edges_ast_guard.append(edge)

            # 같은 라벨 블록 내부 SB 연결
            if prev_sid is not None:
                self.edges_sb.append((prev_sid, cf, 1))
            prev_sid = cl or cf

        return first_sid, prev_sid

    def _parse_case_int(self, label_str: str, switch_sid: int) -> int:
        """
        '6' -> 6, '0x10' -> 16, '077' -> 0o77, ''A'' -> 65, '\n' -> 10, '\x41' -> 65, L'A' -> 65
        파싱 실패 시 per-switch 안정 매핑(0..N-1)로 폴백.
        """
        s = (label_str or "").strip()
        # 문자 리터럴 처리: 'A', '\n', '\x41', L'A'
        try:
            if s.startswith("L'") and s.endswith("'") and len(s) >= 4:
                s = s[1:]  # L 제거 -> 'A'
            if len(s) >= 3 and s[0] == "'" and s[-1] == "'":
                payload = s[1:-1]
                ch = bytes(payload, "utf-8").decode("unicode_escape")
                return ord(ch[0]) if ch else 0
            # 16진
            if s.lower().startswith(("+0x", "-0x", "0x")):
                return int(s, 16)
            # 8진 (0으로 시작, 0/±0은 아래 10진 경로에서도 동작)
            if re.fullmatch(r"[+-]?0[0-7]+", s):
                return int(s, 8)
            # 10진
            return int(s, 10)
        except Exception:
            pass
        # 폴백: 드문 복잡식은 스위치별 안정 매핑으로 유지
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
        # 예: "case 7:" → "7"
        if code.lower().startswith("case"):
            s = code[len("case") :].strip()
            if s.endswith(":"):
                s = s[:-1].strip()
            return s or "case"
        return code or "case"

    def _find_switch_body(self, sw_node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        # 다양한 AST 변형 대비: CompoundStatement / BlockStatement 우선
        for k in sw_node.get("children") or []:
            if isinstance(k, dict) and k.get("nodeType") in {"CompoundStatement", "BlockStatement"}:
                return k
        return None

    def _extract_switch_condition_code(self, sw_node: Dict[str, Any]) -> str:
        # 조건식만 뽑아 code로 사용 (전량 pretty-printed code 금지)
        # 보통 children 중 CompoundStatement가 아닌 첫 노드가 조건식
        for k in sw_node.get("children") or []:
            if isinstance(k, dict) and k.get("nodeType") not in {
                "CompoundStatement",
                "BlockStatement",
                "CaseLabel",
                "DefaultLabel",
            }:
                return str(k.get("code", ""))
        # fallback
        code = str(sw_node.get("code", ""))
        # "switch(7) { ... }" 형태면 괄호 안만 대충 추출
        try:
            open_paren = code.find("(")
            close_paren = code.find(")")
            if 0 <= open_paren < close_paren:
                return code[open_paren + 1 : close_paren]
        except Exception:
            pass
        return str(code)

    def _guards_from_condition_ast(self, cond_ast: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """
        조건식 AST에서 변수별 가드 증거를 추출한다.
        반환 예:
        {"data": {"lower":1, "upper":1, "upper_const":0.1}}
        규칙:
        - x>=0, x>0 -> lower=1
        - x<=K, x<K (K=정수리터럴) -> upper=1, upper_const=norm_val(K)
        - AND(&&)는 양쪽 모두 병합, OR(||)는 보수적으로 '합집합' 병합
        - 좌변/우변 뒤집힘(예: 0 < x, 10 > x)도 처리
        - 식별자는 Identifier 또는 MemberAccess(base.field) 허용
        - 비상수 상계(예: x < N)는 upper=1만 줄지, upper_const는 0.0 유지(정규화 불가)
        """
        out: Dict[str, Dict[str, Any]] = {}

        # ---------- helpers ----------
        def _norm_val(k: int) -> float:
            try:
                k = int(k)
                if k <= 0:
                    return 0.0
                # 프로젝트 일관: 10 -> 0.1 로 보이니 1/k 채택
                return 1.0 / float(k)
            except Exception:
                return 0.0

        def _is_int_literal(n: Dict[str, Any]) -> bool:
            if not isinstance(n, dict):
                return False
            if n.get("nodeType") in {"Literal", "IntegerLiteral", "NumberLiteral"}:
                t = (n.get("type") or "").lower()
                return "int" in t or t == ""  # 일부 파서에서 type 비울 수 있음
            return False

        def _int_from_node(n: Optional[Dict[str, Any]]) -> int | None:
            # Literal("10"), 혹은 Unary - Literal("10")
            if not isinstance(n, dict):
                return None
            if _is_int_literal(n):
                v = n.get("value")
                try:
                    return int(str(v).strip())
                except Exception:
                    # fallback: 코드에서 추출
                    code = n.get("code", "")
                    import re

                    m = re.search(r"-?\d+", code)
                    return int(m.group(0)) if m else None
            # Unary - <literal>
            if n.get("nodeType") in {"UnaryOperator", "UnaryExpression"} and n.get("operator") == "-":
                kids = n.get("children") or []
                k0 = kids[0] if kids else None
                val = _int_from_node(k0)
                return -val if isinstance(val, int) else None
            # 괄호로 감싼 케이스 (ParenthesizedExpression 류)
            if n.get("nodeType") in {"ParenExpression", "ParenthesizedExpression"}:
                ks = n.get("children") or []
                return _int_from_node(ks[0]) if ks else None
            return None

        def _ident_name(n: Optional[Dict[str, Any]]) -> str | None:
            if not isinstance(n, dict):
                return None
            nt = n.get("nodeType")
            if nt == "Identifier":
                nm = n.get("name")
                return nm if isinstance(nm, str) and nm else None
            if nt == "MemberAccess":
                kids = n.get("children") or []
                base = kids[0] if len(kids) > 0 else None
                field = kids[1] if len(kids) > 1 else None
                b = _ident_name(base)
                f = _ident_name(field)
                if b and f:
                    return f"{b}.{f}"
                return b or f
            # 괄호/캐스트로 감싼 경우 풀어주기
            if nt in {
                "ParenExpression",
                "ParenthesizedExpression",
                "CStyleCastExpression",
                "CXXStaticCastExpr",
                "UnaryOperator",
                "UnaryExpression",
            }:
                kids = n.get("children") or []
                return _ident_name(kids[0]) if kids else None
            return None

        def _emit_lower(var: str) -> None:
            if not var:
                return
            e = out.setdefault(var, {"lower": 0, "upper": 0, "upper_const": 0.0})
            e["lower"] = 1

        def _emit_upper(var: str, k: int | None) -> None:
            if not var:
                return
            e = out.setdefault(var, {"lower": 0, "upper": 0, "upper_const": 0.0})
            e["upper"] = 1
            if isinstance(k, int):
                e["upper_const"] = max(e["upper_const"], _norm_val(k))  # 최대값 유지

        # ---------- recursive visit ----------
        def visit(n: Optional[Dict[str, Any]]) -> None:
            if not isinstance(n, dict):
                return
            nt = n.get("nodeType")
            if nt == "BinaryExpression":
                op = n.get("operator")
                ch = n.get("children") or []
                a = ch[0] if len(ch) > 0 else None
                b = ch[1] if len(ch) > 1 else None

                # 논리연산: && / ||
                if op in {"&&", "and", "AND"}:
                    visit(a)
                    visit(b)
                    return
                if op in {"||", "or", "OR"}:
                    # 보수적으로 두 쪽 모두 반영(합집합)
                    visit(a)
                    visit(b)
                    return

                # 비교연산
                if op in {"<", "<=", ">", ">="}:
                    # 케이스 1) var ? const
                    v_left = _ident_name(a)
                    k_right = _int_from_node(b)

                    # 케이스 2) const ? var  (좌우 뒤집힘)
                    k_left = _int_from_node(a)
                    v_right = _ident_name(b)

                    if v_left:
                        if op in {">", ">="}:
                            # x > 0, x >= 0 → lower
                            if (k_right is not None) and k_right == 0:
                                _emit_lower(v_left)
                        elif op in {"<", "<="}:
                            # x < K, x <= K → upper(+const)
                            _emit_upper(v_left, k_right)
                        return

                    if v_right:
                        # 뒤집힌 비교는 연산자 방향 반대로 해석
                        if op in {">", ">="}:
                            # K > x ⇒ x < K
                            _emit_upper(v_right, k_left)
                        elif op in {"<", "<="}:
                            # K < x ⇒ x > K  (K가 0일 때만 lower 인정; 일반 K는 무시)
                            if (k_left is not None) and k_left == 0:
                                _emit_lower(v_right)
                        return

                    # 둘 다 변수/상수 아니면 스킵
                    return

            # 괄호/캐스트/단항은 내부로
            if nt in {
                "ParenExpression",
                "ParenthesizedExpression",
                "CStyleCastExpression",
                "CXXStaticCastExpr",
                "UnaryOperator",
                "UnaryExpression",
            }:
                for c in n.get("children") or []:
                    visit(c)
                return

            # 논리식이 다른 노드(예: ConditionalOperator 등)면 하위 탐색
            for c in n.get("children") or []:
                visit(c)

        visit(cond_ast)

        return out

    def _guards_from_for_header(self, for_ast: Dict[str, Any]) -> Dict[str, Any]:
        """
        for (init; cond; inc) 에서 init/inc를 읽어 하한 가드(lower)를 보강.
        - init:  i = K (K가 정수리터럴이며 K>=0)
        - inc :  i++, ++i, i += k (k>=0)  → 단조 증가가 보장될 때만 lower=1 부여
        반환 예: {"i": {"lower":1, "upper":0, "upper_const":0.0}}
        """
        out: Dict[str, Dict[str, Any]] = {}

        def _emit_lower(v: Optional[str]) -> None:
            if not v:
                return
            e = out.setdefault(v, {"lower": 0, "upper": 0, "upper_const": 0.0})
            e["lower"] = 1

        if not isinstance(for_ast, dict) or for_ast.get("nodeType") != "ForStatement":
            return out

        kids = for_ast.get("children") or []
        init = kids[0] if len(kids) >= 1 else None
        inc = kids[2] if len(kids) >= 3 else None

        # helper: 정수리터럴 추출
        def _int_from(n: Any) -> Optional[int]:
            if not isinstance(n, dict):
                return None
            if n.get("nodeType") in {"Literal", "IntegerLiteral", "NumberLiteral"}:
                try:
                    return int(str(n.get("value")).strip())
                except TypeError, ValueError:
                    return None
            if n.get("nodeType") in {"UnaryOperator", "UnaryExpression"} and n.get("operator") == "-":
                ks = n.get("children") or []
                v = _int_from(ks[0]) if ks else None
                return -v if isinstance(v, int) else None
            if n.get("nodeType") in {"ParenExpression", "ParenthesizedExpression"}:
                ks = n.get("children") or []
                return _int_from(ks[0]) if ks else None
            return None

        # helper: 식별자 이름 추출 (Identifier/MemberAccess)
        def _ident(n: Any) -> Optional[str]:
            if not isinstance(n, dict):
                return None
            nt = n.get("nodeType")
            if nt == "Identifier":
                nm = n.get("name")
                return nm if isinstance(nm, str) and nm else None
            if nt == "MemberAccess":
                ks = n.get("children") or []
                b = _ident(ks[0] if len(ks) > 0 else None)
                f = _ident(ks[1] if len(ks) > 1 else None)
                return f"{b}.{f}" if b and f else (b or f)
            if nt in {
                "ParenExpression",
                "ParenthesizedExpression",
                "CStyleCastExpression",
                "CXXStaticCastExpr",
                "UnaryOperator",
                "UnaryExpression",
            }:
                ks = n.get("children") or []
                return _ident(ks[0]) if ks else None
            return None

        # 1) init: i = K (K>=0)
        init_var = None
        init_nonneg = False
        if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression" and init.get("operator") == "=":
            ch = init.get("children") or []
            lhs, rhs = (ch[0] if len(ch) > 0 else None), (ch[1] if len(ch) > 1 else None)
            init_var = _ident(lhs)
            kv = _int_from(rhs)
            init_nonneg = isinstance(kv, int) and kv >= 0

        # 2) inc: ++i / i++ / i += k (k>=0)
        inc_var = None
        inc_nondecreasing = False
        if isinstance(inc, dict):
            nt = inc.get("nodeType")
            if nt in {"UnaryOperator", "UnaryExpression"} and inc.get("operator") in {"++"}:
                ks = inc.get("children") or []
                inc_var = _ident(ks[0]) if ks else None
                inc_nondecreasing = True
            elif nt == "AssignmentExpression" and inc.get("operator") in {"+="}:
                ch = inc.get("children") or []
                lhs, rhs = (ch[0] if len(ch) > 0 else None), (ch[1] if len(ch) > 1 else None)
                inc_var = _ident(lhs)
                step = _int_from(rhs)
                inc_nondecreasing = isinstance(step, int) and step >= 0

        # 3) 결론: init와 inc가 같은 변수이고 init_nonneg & inc_nondecreasing면 lower=1
        if init_var and inc_var and init_var == inc_var and init_nonneg and inc_nondecreasing:
            _emit_lower(init_var)

        return out

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
        """Statement-level node creation + inject AST-GNN 'training feat' / 'debug info' separately.
        - DFG-GNN specific features (e.g. is_buffer_access, is_sink_assign) are NEVER added here.
        - node_type_id is stored as an integer ID for direct use in model embedding.
        - Break/Continue (and Return if needed) are excluded from training (train_mask=0).
        """
        sid = self.sid_counter
        self.sid_counter += 1

        # --- 호출 노드면 AST 기반으로 의미/플래그 계산, 아니면 중립 플래그 ---
        if node_type in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
            call_sem_cat_id = call_sem_cat_id_from_name(name_hint) if name_hint else 0

            raw_ast = self.idmap.get(orig_id) if isinstance(orig_id, int) else None
            # 1) 인자 리스트 노드면 그대로 사용
            call_ast = None
            if isinstance(raw_ast, dict) and raw_ast.get("nodeType") in {"ParameterList", "ArgumentList"}:
                call_ast = raw_ast
            # 2) 호출 노드면 그대로 사용
            elif isinstance(raw_ast, dict) and raw_ast.get("nodeType") in {
                "CallExpression",
                "StandardLibCall",
                "UserDefinedCall",
            }:
                call_ast = raw_ast
            # 3) 그 외에는 안전하게 부모로 상승(루프 가드 있음)
            elif isinstance(raw_ast, dict):
                call_ast = self._nearest_call_node(raw_ast)

            call_flags = self.compute_call_flags(fname=name_hint, call_ast=call_ast, code=code)

        else:
            call_sem_cat_id = 0
            call_flags = {
                "call_flag_danger_unbounded": 0,
                "call_flag_len_linked_to_dst": 0,
                "call_flag_sizeof_non_dst": 0,
                "call_flag_has_varargs": 0,
                # Calculate AST enhancement flags related to calls
                "call_dst_is_field": 0,
                "call_size_kind": 0,
                "call_len_linked_to_dst_extended": 0,
                "call_size_is_sizeof_base_struct": 0,
                "call_size_mismatch_field": 0,
                "alloc_sizeof_state": 0,
            }

        # Buffer declaration context
        is_buf_decl = 1 if node_type == "ArrayDeclaration" else 0
        if is_buf_decl:
            buf_state, buf_norm = parse_array_size_state_and_norm(code)
        else:
            buf_state, buf_norm = (0, 0.0)

        # 노드 컨텍스트 가드 강도
        ctx_strength = (1 if guard_lower else 0) + (2 if guard_upper else 0)

        # 학습 마스킹
        train_mask = 1
        if node_type in {"BreakStatement", "ContinueStatement"}:
            train_mask = 0

        # --- 학습용 feat ---
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
            # AST-GNN 보강 피처
            "call_dst_is_field": call_flags["call_dst_is_field"],
            "call_size_kind": call_flags["call_size_kind"],
            "call_len_linked_to_dst_extended": call_flags["call_len_linked_to_dst_extended"],
            "call_size_is_sizeof_base_struct": call_flags["call_size_is_sizeof_base_struct"],
            "call_size_mismatch_field": call_flags["call_size_mismatch_field"],
            "alloc_sizeof_state": call_flags["alloc_sizeof_state"],
        }

        # 상위 row
        row = {
            "sid": sid,
            "node_type": node_type,
            "code": (code or "").strip(),
            "orig_id": orig_id,
            "feat": feat,
        }
        # debug는 있을 때만
        if debug_extra:
            row["debug"] = dict(debug_extra)

        self.nodes.append(row)
        if isinstance(orig_id, int):
            self.id2sid[orig_id] = sid

        return sid

    def compute_call_flags(
        self, fname: str | None = None, call_ast: Optional[Dict[str, Any]] = None, code: str | None = None
    ) -> Dict[str, int]:
        """
        AST-GNN 전용 호출 플래그 계산 (AST JSON 스키마 우선, 문자열 폴백)
        - len-linked: sizeof(dst|*dst|dst[0]|base.field)일 때만 1
        - sizeof_non_dst: sizeof(...)가 있으면서 위 연계 패턴에 안 맞으면 1
        - call_size_kind:
            0: 없음, 1: 정수 리터럴, 2: 비상수식, 3: sizeof 단독, 4: sizeof 포함 산술식
        """
        import re

        # ---------- 유틸 (AST/문자열 혼용) ----------
        def _norm(x: str) -> str:
            return re.sub(r"\s+", "", x or "")

        def _code(n: Optional[Dict[str, Any]]) -> str:
            return (n.get("code") if isinstance(n, dict) else "") or ""

        def _contains_sizeof_node(n: Optional[Dict[str, Any]]) -> bool:
            if not isinstance(n, dict):
                return False
            if "sizeof(" in _code(n):
                return True
            # 파서에 따라 SizeOfExpression nodeType이 있는 경우
            if n.get("nodeType") in {"SizeOfExpression", "SizeofExpr", "SizeofExpression"}:
                return True
            for c in n.get("children") or []:
                if isinstance(c, dict) and _contains_sizeof_node(c):
                    return True
            return False

        def _size_kind_ast(size_node: Optional[Dict[str, Any]]) -> int:
            """AST 기반 size kind 판정; 어려우면 문자열 폴백."""
            if not isinstance(size_node, dict):
                return 0
            s = _code(size_node)
            if not s:
                return 0
            if _contains_sizeof_node(size_node):
                # sizeof(...) 토큰을 치환 후 연산자 남는지 확인 (문자열 폴백)
                sz_repl = re.sub(r"\bsizeof\s*\([^()]*\)", "SZ", _norm(s))
                return 4 if re.search(r"[+\-*/]", sz_repl) else 3
            # 리터럴 정수?
            return 1 if re.fullmatch(r"\d+", _norm(s)) else 2

        def _dst_is_field_from_ast(dst_node: Optional[Dict[str, Any]]) -> Tuple[int, str, str]:
            """dst가 base.field / base->field인지 판정. (is_field, base, fieldName)"""
            if not isinstance(dst_node, dict):
                return 0, "", ""
            full = self._fullname_from_expr(dst_node) or ""
            if "->" in full:
                base = full.split("->", 1)[0]
                field = full.split("->", 1)[1]
                return 1, base, field
            if "." in full:
                base = full.split(".", 1)[0]
                field = full.split(".", 1)[1]
                return 1, base, field
            return 0, "", ""

        def _idents_of(node: Optional[Dict[str, Any]]) -> Set[str]:
            try:
                return set(self._idents_from_ast_node(node, skip_sizeof=True, skip_callee=True))
            except Exception:
                return set()

        def _unwrap_dst(node: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
            """&/캐스트/괄호 제거해 실제 dst를 얻음."""
            try:
                return self._unwrap_ast(node, strip_addr=True, strip_cast=True, strip_paren=True)
            except Exception:
                return node

        # ---------- 초기 플래그 ----------
        flags: Dict[str, int] = {
            "call_flag_danger_unbounded": 0,
            "call_flag_len_linked_to_dst": 0,
            "call_flag_sizeof_non_dst": 0,
            "call_flag_has_varargs": 0,
            "alloc_sizeof_state": 0,
            "call_dst_is_field": 0,
            "call_size_kind": 0,
            "call_len_linked_to_dst_extended": 0,
            "call_size_is_sizeof_base_struct": 0,
            "call_size_mismatch_field": 0,
        }

        low = (fname or "").lower()

        # varargs (printf 계열)
        if low in {"printf", "fprintf", "vprintf", "vfprintf", "sprintf", "snprintf", "vsprintf", "vsnprintf"}:
            flags["call_flag_has_varargs"] = 1

        # 위험(unbounded) - 외부 세트 있으면 사용, 없으면 기본
        UNBOUNDED_LOCAL = set(getattr(self, "UNBOUNDED", {"gets", "strcpy", "strcat", "sprintf", "vsprintf"}))
        if low in UNBOUNDED_LOCAL:
            flags["call_flag_danger_unbounded"] = 1

        # alloc sizeof state
        if low in {"malloc", "calloc", "realloc", "alloca", "_alloca", "ALLOCA", "new", "new[]"}:
            # AST가 있으면 모든 인자에서 sizeof 존재 여부 확인
            if isinstance(call_ast, dict):
                kids = self._get_call_args_from_ast(call_ast)
                joined = ",".join(_code(k) for k in kids)
            else:
                # 문자열 폴백
                args = []
                if code:
                    open_paren, close_paren = code.find("("), code.rfind(")")
                    sig = (
                        code[open_paren + 1 : close_paren]
                        if (open_paren != -1 and close_paren != -1 and close_paren > open_paren)
                        else ""
                    )
                    args = [p.strip() for p in sig.split(",")] if sig else []
                joined = ",".join(args)
            flags["alloc_sizeof_state"] = 2 if re.search(r"\bsizeof\s*\(", joined) else 1

        # ---------- dst/size 슬롯 결정 ----------
        def _slot_from_ast(
            name: str, args: List[Dict[str, Any]]
        ) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
            n = (name or "").lower()
            if n in {"memcpy", "memmove", "strncpy"} and len(args) >= 3:
                return args[0], args[2]
            if n in {"memset"} and len(args) >= 3:
                return args[0], args[2]
            if n in {"snprintf", "vsnprintf"} and len(args) >= 2:
                return args[0], args[1]
            if n in {"fgets"} and len(args) >= 2:
                return args[0], args[1]
            if n in {"read", "recv"} and len(args) >= 3:
                return args[1], args[2]
            if n in {"connect"} and len(args) >= 3:
                return args[1], args[2]  # addr, addrlen
            return None, None

        # ---------- 본체: AST 경로 ----------
        if isinstance(call_ast, dict):
            ast_args = self._get_call_args_from_ast(call_ast)

            dst_node, size_node = _slot_from_ast(fname or "", ast_args)

            # size kind
            flags["call_size_kind"] = _size_kind_ast(size_node)

            # dst 필드 여부/베이스명
            dst_core = _unwrap_dst(dst_node)
            is_field, base_name, field_name = _dst_is_field_from_ast(dst_core)
            flags["call_dst_is_field"] = is_field

            # len-linked / sizeof_non_dst / 필드 mismatch
            if isinstance(size_node, dict):
                size_code = _code(size_node)
                sizeof_present = "sizeof(" in size_code
                linked = False

                # dst 식별자/풀네임 수집
                dst_names = _idents_of(dst_core)
                dst_full = self._fullname_from_expr(dst_core) or ""
                if dst_full:
                    dst_names.add(dst_full)

                # 기본 링크: sizeof(dst) | sizeof(*dst) | sizeof(dst[0])
                if size_code and dst_names:
                    for dn in dst_names:
                        if (
                            f"sizeof({dn})" in size_code
                            or f"sizeof(*{dn})" in size_code
                            or f"sizeof({dn}[0])" in size_code
                        ):
                            linked = True
                            break

                # 확장 링크: sizeof(base.field)
                linked_ext = False
                if is_field and base_name and field_name:
                    pat_field = rf"\bsizeof\s*\(\s*{re.escape(base_name)}\s*\.\s*{re.escape(field_name)}\s*\)\s*"
                    if re.search(pat_field, size_code):
                        linked_ext = True
                    # sizeof(base) → base 전체
                    pat_base = rf"\bsizeof\s*\(\s*{re.escape(base_name)}\s*\)\s*"
                    if re.search(pat_base, size_code):
                        flags["call_size_is_sizeof_base_struct"] = 1

                if linked or linked_ext:
                    flags["call_flag_len_linked_to_dst"] = 1
                if linked_ext:
                    flags["call_len_linked_to_dst_extended"] = 1

                if sizeof_present and not (linked or linked_ext):
                    flags["call_flag_sizeof_non_dst"] = 1

                # 필드 dst인데 size가 필드와 불연계/베이스 전체면 mismatch
                if is_field:
                    if flags["call_size_is_sizeof_base_struct"] == 1 or (
                        sizeof_present
                        and flags["call_flag_len_linked_to_dst"] == 0
                        and flags["call_len_linked_to_dst_extended"] == 0
                    ):
                        flags["call_size_mismatch_field"] = 1

            # connect: len-linked는 의미 없음(메모리 dst 개념 아님) → 위 계산값 그대로 둠
            return flags

        # Fallback: no usable call AST, so no flags can be derived.
        #
        # This used to call `self._compute_call_flags_fallback(...)`, a
        # string-parsing path that does not exist on this class -- it was lost
        # in the TypeScript migration. Any caller reaching here (i.e. passing
        # call_ast=None) got an AttributeError, not flags. Returning the neutral
        # flag set is what every other "cannot determine" branch does.
        flags = self._zero_call_flags()
        if (fname or "").lower() in UNBOUNDED_CALLS:
            flags["call_flag_danger_unbounded"] = 1
        return flags

    # ---- AST helpers
    def _find_first_call_node(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(node, dict):
            return None
        nt = node.get("nodeType")
        if nt in CALL_NODE_TYPES:
            # ✅ 매크로 상수 호출은 스킵
            if not self._is_macro_constant_call(node):
                return node
            # continue search in children
        for ch in node.get("children") or []:
            if isinstance(ch, dict):
                f = self._find_first_call_node(ch)
                if f is not None:
                    return f
        return None

    def _nearest_call_node(self, node: Optional[Dict[str, Any]], max_hops: int = 64) -> Optional[Dict[str, Any]]:
        """노드에서 위로 올라가 가장 가까운 호출 노드를 찾는다(루프 가드 포함)."""
        cur = node
        seen = set()
        hops = 0
        while isinstance(cur, dict) and cur.get("nodeType") not in CALL_NODE_TYPES:
            nid = cur.get("id")
            if not isinstance(nid, int):
                # Without an int id there is no parent entry to follow, and the
                # lookup below would have returned None anyway.
                return None
            if nid in seen:
                # guard against self-loops
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
        """
        조건식 AST 안에서 '첫 호출'을 찾아 Statement 노드로 리프팅해 If 앞에 배치.
        반환: (new_sb_prev, lifted_call_sid)  // 없으면 (sb_prev, None)
        정책:
        - 매크로 상수 호출(#define …)은 리프팅하지 않음.
        - 부작용 있는 API만 리프팅(sem_id ∈ LIFTABLE_SEM_CATS).
        - (옵션) 순수 파서(atoi/strtol)도 리프팅하려면 self.LIFT_PURE_COND_CALLS=True로.
        - 이미 동일 orig_id로 노드가 존재하면 재사용(중복 생성 방지).
        - 리프팅된 호출에는 guard 에지 부여하지 않음(조건 평가 '직전 실행' 개념).
        """
        call_node = self._find_first_call_node(cond_node)
        if not isinstance(call_node, dict):
            return sb_prev, None

        # 매크로 상수 형태(UDC + ParameterList 아래 CompoundStatement)면 스킵
        if self._is_macro_constant_call(call_node):
            return sb_prev, None

        fname = call_node.get("name") or ""
        sem_id = call_sem_cat_id_from_name(fname)  # 0:none, 1:mem_alloc, 2:mem_copy, 3:ext_input, 5:mem_set, 6.. 등

        # 리프팅 대상 필터
        lift_ok = sem_id in LIFTABLE_SEM_CATS
        if not lift_ok and getattr(self, "LIFT_PURE_COND_CALLS", False):
            # 옵션: 순수 파서도 리프팅(예: atoi/strtol 계열: 9/10로 설계했었다면 여기에 반영)
            lift_ok = sem_id in {9, 10}
        if not lift_ok:
            return sb_prev, None

        ctype = call_node.get("nodeType") or "CallExpression"
        if ctype not in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
            ctype = "CallExpression"

        orig_id = call_node.get("id") if isinstance(call_node.get("id"), int) else None

        # 이미 같은 orig_id로 노드가 만들어졌다면 재사용(중복 방지)
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
                upper_norm=0.0,  # 조건 평가 전 실행 → 가드 0
                name_hint=fname,
                orig_id=orig_id,
                debug_extra={"lifted_from_condition": 1},
            )

        # PC: parent → call
        self.edges_pc.append((parent_sid, call_sid, 0))
        # SB: prev → call
        if sb_prev is not None:
            self.edges_sb.append((sb_prev, call_sid, 1))

        # 리프팅된 호출을 새로운 sb 체인의 끝으로 반환
        return call_sid, call_sid

    def _get_call_args_from_ast(self, node: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Call/ParameterList/ArgumentList 어디를 주어도 인자 리스트를 반환."""
        if not isinstance(node, dict):
            return []
        nt = node.get("nodeType")
        # 바로 리스트 노드가 들어온 경우
        if nt in {"ParameterList", "ArgumentList"}:
            return [c for c in (node.get("children") or []) if isinstance(c, dict)]

        # 호출 노드인 경우, 내부 리스트 검색
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

    def _unwrap_ast(
        self,
        node: Optional[Dict[str, Any]],
        strip_addr: bool = False,
        strip_cast: bool = True,
        strip_paren: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """AST 표현식에서 바깥 래핑을 옵션대로 벗겨 내부 '핵심' 표현식을 반환."""
        n = node
        while isinstance(n, dict):
            nt = n.get("nodeType")

            # 우리 AST 스키마에서는 이런 타입이 없음
            # if strip_paren and nt in {"ParenExpression","ParenExpr"}:
            #    kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
            #    n = kids[0] if kids else None
            #    continue

            if strip_cast and nt in {"CastExpression", "CStyleCastExpr"}:
                kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
                n = next((c for c in kids if c.get("nodeType") not in {"TypeRef", "TypeName", "TypeSpecifier"}), None)
                continue

            if strip_addr and (
                nt == "AddressOfExpression" or (nt == "UnaryOperator" and n.get("operator") in {"&", "&amp;"})
            ):
                kids = [c for c in (n.get("children") or []) if isinstance(c, dict)]
                n = kids[0] if kids else None
                continue
            break
        return n

    # 헬퍼: 주어진 AST id 아래에서 평탄화된 "첫 문장" sid 찾기
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
        """
        매크로 상수(#define NAME …)가 호출처럼 모델링된 특이 케이스를 식별.
        특징: Call/UDC 노드의 ParameterList/ArgumentList 아래에 CompoundStatement가 바로 자식으로 존재.
        """
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
        """
        주어진 서브트리(node)에 C의 `sizeof` 사용이 포함되어 있으면 True.
        탐지 규칙:
          1) 정규 AST 노드: SizeOfExpression / SizeOf / TypeSizeOf / UnarySizeOf
          2) 단항 연산자 형태: operator/op == 'sizeof'
          3) 비정규 인코딩: Identifier/CallExpression의 name == 'sizeof'
          4) 매크로/텍스트 폴백: code 문자열에 'sizeof(' 포함
        """
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

            # 1) canonical sizeof node types
            if nt in {"SizeOfExpression", "SizeOf", "TypeSizeOf", "UnarySizeOf"}:
                return True

            # 2) unary-operator form
            if op == "sizeof":
                return True

            # 3) odd encodings (identifier/call named 'sizeof')
            if name == "sizeof":
                return True

            # 4) macro/text fallback
            if "sizeof(" in code:
                return True

            # descend
            for ch in n.get("children") or []:
                if isinstance(ch, dict):
                    stack.append(ch)

        return False

    def _code_of(self, node: Any, default: str = "") -> str:
        """
        가능한 한 안정적으로 AST 노드의 '표면 코드'를 복원한다.
        우선순위: node.code → 노드 타입별 재구성 → 자식 결합 → default
        반환은 trim되지만 내부 공백은 보존한다.
        """
        if node is None:
            return default
        if isinstance(node, str):
            return node.strip()
        if not isinstance(node, dict):
            return default

        # 0) Use the node's own code when present.
        c = node.get("code")
        if isinstance(c, str) and c.strip():
            return c.strip()

        # The per-type reconstruction and child-concatenation steps promised by
        # the docstring were lost in the migration. Until they exist, fall back
        # to `default` -- previously this fell off the end and returned None to
        # callers annotated `-> str`.
        return default

    def _is_macro_const_call(self, node: Any) -> bool:
        """UserDefinedCall + ParameterList + CompoundStatement + Literal… pattern -> macro constant."""
        if not isinstance(node, dict) or (node.get("nodeType") != "UserDefinedCall"):
            return False
        kids = node.get("children") or []
        if not kids:
            return False
        plist = kids[0] if isinstance(kids[0], dict) and kids[0].get("nodeType") == "ParameterList" else None
        if not plist:
            return False
        # find CompoundStatement with only literals (or nested trivial nodes)
        stack = [plist]
        while stack:
            n = stack.pop()
            if not isinstance(n, dict):
                continue
            if n.get("nodeType") == "CompoundStatement":
                # consider macro-constant if it has a Literal descendant
                for ch in n.get("children") or []:
                    if isinstance(ch, dict) and ch.get("nodeType") in {
                        "Literal",
                        "StringLiteral",
                        "IntegerLiteral",
                        "CharacterLiteral",
                    }:
                        return True
            for ch in n.get("children") or []:
                if isinstance(ch, dict):
                    stack.append(ch)
        return False

    def _macro_literal(self, node: Any) -> Any:
        """Return the first Literal node under the macro call node; else None."""
        if not isinstance(node, dict):
            return None
        # accept UserDefinedCall and its ParameterList subtree
        root = node
        if node.get("nodeType") == "UserDefinedCall":
            kids = node.get("children") or []
            root = kids[0] if kids and isinstance(kids[0], dict) else node
        stack = [root]
        while stack:
            n = stack.pop()
            if not isinstance(n, dict):
                continue
            if n.get("nodeType") in {"Literal", "StringLiteral", "IntegerLiteral", "CharacterLiteral"}:
                return n
            for ch in n.get("children") or []:
                if isinstance(ch, dict):
                    stack.append(ch)
        return None

    def _resolve_macro_like_expr(self, node: Any) -> Any:
        """If node is a macro-constant call, return its literal node; otherwise original node."""
        try:
            if isinstance(node, dict) and node.get("nodeType") == "UserDefinedCall" and self._is_macro_const_call(node):
                lit = self._macro_literal(node)
                if isinstance(lit, dict):
                    return lit
        except Exception:
            pass
        return node

    # -------------------------------------------------
    # DFGExtractor에도 있는 Helper 함수
    # ---------------------------------------------------
    def _idents_from_ast_node(self, n: Any, *, skip_sizeof: bool = True, skip_callee: bool = True) -> List[str]:
        """
        AST 서브트리에서 '식별자 토큰'을 수집한다.
        - field-sensitivity: MemberAccess는 'base.field[.sub...]' 하나의 토큰으로 수집
        - ArraySubscript: base는 풀네임(필드 포함) 1토큰, index는 재귀 수집
        - Cast/Paren/Unary(&,*)/PointerDereference 등은 '껍질'만 벗겨 내부 식으로 재귀
        - Call: 함수 이름은 변수 아님 → 기본(skip_callee=True)에서는 수집 안 함, 인자만 재귀
        - sizeof(...)는 런타임 의존 아님 → 기본(skip_sizeof=True)일 때 내부 식별자 수집 안 함
        반환: 리스트(중복 제거, 입력 순서 보존)
        """
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
            """이 노드 자체가 sizeof(...) 표현인지 판별."""
            if not is_dict(x):
                return False
            nt = node_type(x)
            if nt in {"SizeOfExpr", "UnaryExprOrTypeTraitExpr", "UnaryExpressionOrTypeTraitExpr"}:
                return True
            code = x.get("code")
            if isinstance(code, str) and re.match(r"^\s*sizeof\s*\(", code):
                # 노드 자체가 sizeof(...) 한 덩어리인 경우에만 True
                return True
            return False

        def walk(x: Any) -> None:
            if not is_dict(x):
                return

            # sizeof(...)는 요청 시 내부를 보지 않는다
            if skip_sizeof and is_sizeof_node(x):
                return

            nt = node_type(x)

            # Identifier
            if nt == "Identifier":
                emit(x.get("name"))
                return

            # MemberAccess: 'base.field[.sub...]' 풀네임 1토큰으로
            if nt == "MemberAccess":
                try:
                    full = self._fullname_from_expr(x)  # e.g., 's.charFirst' / 'a.b.c'
                except Exception:
                    full = None
                if full:
                    emit(full)
                    return
                # 풀네임을 못 만들면 일반 재귀
                for c in children(x):
                    walk(c)
                return

            # ArraySubscriptExpression: base 풀네임 + index 재귀
            if nt == "ArraySubscriptExpression":
                kids = children(x)
                base = kids[0] if len(kids) > 0 else None
                idx = kids[1] if len(kids) > 1 else None
                if is_dict(base):
                    # base는 가능하면 풀네임 1개만 기록
                    try:
                        base_full = self._fullname_from_expr(base)
                    except Exception:
                        base_full = None
                    if base_full:
                        emit(base_full)
                    else:
                        # 풀네임 못 만들면 내부로 재귀
                        walk(base)
                if is_dict(idx):
                    walk(idx)
                return

            # Call: 함수 이름은 변수 아님(기본은 스킵), 인자 리스트만 재귀
            if nt in {"UserDefinedCall", "StandardLibCall", "CallExpression"}:
                """
                Find UserDefinedCall/StandardLibCall within cond_node of condition (If/For/While/Switch)
                and lift as a node before the condition statement.
                """
                if not skip_callee:
                    emit(x.get("name"))  # 함수명을 변수처럼 취급하고 싶을 때만
                for c in children(x):
                    walk(c)
                return

            # PointerDereference / AddressOf / Paren / Cast / UnaryOperator → 내부로 재귀
            if nt in {"PointerDereference", "AddressOf", "ParenExpression", "CastExpression", "UnaryOperator"}:
                for c in children(x):
                    walk(c)
                return

            # 그 외 일반 노드: 자식들 재귀
            for c in children(x):
                walk(c)

        walk(n)
        return out

    def _fullname_from_expr(self, n: Any) -> Optional[str]:
        """Return identifier (with field-sensitivity, e.g., 's.charFirst') from an expression.
        Handles PointerDereference/Unary '*'/'&', Cast/Paren, and ArraySubscript base.
        """
        # 0) null/primitive guard
        if n is None:
            return None

        # 1) unwrap cast/paren first
        n = self._unwrap_ast(n, strip_cast=True)

        # 2) if array subscript, resolve its base first-child
        if isinstance(n, dict) and n.get("nodeType") == "ArraySubscriptExpression":
            kids = n.get("children") or []
            n = kids[0] if kids else n
            n = self._unwrap_ast(n, strip_cast=True)

        # 3) peel pointer dereference or address-of to reach the underlying lvalue
        while isinstance(n, dict) and (
            n.get("nodeType") == "PointerDereference"
            or (n.get("nodeType") in {"UnaryOperator", "UnaryExpression"} and n.get("operator") in {"*", "&"})
        ):
            kids = n.get("children") or []
            n = kids[0] if kids else n
            n = self._unwrap_ast(n, strip_cast=True)

        # 4) member access wins (field-sensitivity)
        if self._is_member_access(n):
            return self._member_parts(n)[2]

        # 5) plain identifier
        if isinstance(n, dict) and n.get("nodeType") == "Identifier":
            return n.get("name")

        return None

    # --------------------------------------------------------------------
    # Field-sensitive helpers (MemberAccess / MemberExpression)
    # --------------------------------------------------------------------

    def _is_member_access(self, n: Any) -> bool:
        return isinstance(n, dict) and n.get("nodeType") == "MemberAccess"

    def _member_parts(self, n: Any) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """Return (base_name, field_name, full_name='base.field') for a member access node."""
        if not self._is_member_access(n):
            return None, None, None
        kids = n.get("children") or []
        base = kids[0] if len(kids) > 0 else None
        field = kids[1] if len(kids) > 1 else None
        base_name = base.get("name") if isinstance(base, dict) and base.get("nodeType") == "Identifier" else None
        field_name = field.get("name") if isinstance(field, dict) and field.get("nodeType") == "Identifier" else None
        full = f"{base_name}.{field_name}" if base_name and field_name else None
        return base_name, field_name, full

    # --- Added: emit ParameterDeclaration as prologue statements (statement-level nodes) ---
    def _emit_param_statements_prologue(self) -> None:
        """Create statement-level nodes for each ParameterDeclaration under the function AST root.
        - PC: FunctionEntry(sid=0) -> Param1 -> Param2 (chain through SB as well)
        - No guard edges are created here.
        This is a no-op if no ParameterList exists or if params already emitted.
        """
        try:
            func = self.ast
            if not isinstance(func, dict):
                return
            # Locate ParameterList (or ArgumentList fallback)
            plist = None
            for ch in func.get("children") or []:
                if isinstance(ch, dict) and ch.get("nodeType") in {"ParameterList", "ArgumentList"}:
                    plist = ch
                    break
            if not isinstance(plist, dict):
                return

            entry_sid = 0  # FunctionEntry sid is fixed to 0 in this extractor
            prev_sid = None
            for p in plist.get("children") or []:
                if not isinstance(p, dict) or p.get("nodeType") != "ParameterDeclaration":
                    continue
                orig_id = p.get("id") if isinstance(p.get("id"), int) else None
                # Skip if this orig_id already mapped to some sid (avoid duplicate emission)
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
                # AST edges
                self.edges_pc.append((entry_sid, sid, 0))  # PC: entry -> param
                if prev_sid is not None:
                    self.edges_sb.append((prev_sid, sid, 1))  # SB within prologue
                prev_sid = sid
        except Exception:
            # best-effort; never fail extractor due to params
            return
