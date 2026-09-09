import logging
import re
from collections import defaultdict, deque
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from ..knowledge.c_stdlib import BOUNDED, UNBOUNDED, dfg_sink_slots
from ..nodes import (
    GUARD_KINDS,
    GUARD_KIND_IF,
    GUARD_KIND_LOOP,
    ARGLIST_NODE_TYPES,
    ARRAY_DECL_NODE_TYPES,
    CALL_NODE_TYPES,
    CONTAINER_WRITE_NODE_TYPES,
    SIMPLE_DECL_NODE_TYPES,
    STATEMENT_CALL_NODE_TYPES,
    fullname_from_expr,
    guards_from_condition_ast,
    guards_from_for_header,
    unwrap_ast,
    unwrap_cast_paren,
)
from .state import (
    KEYWORDS,
    AssignmentTarget,
    DefUseAccumulator,
    StatementScope,
)

logger = logging.getLogger(__name__)
FUNCTION_META = {"FunctionEntry", "FunctionDeclaration", "FunctionDefinition"}
CONTROL_NODES = {"IfStatement", "ForStatement", "WhileStatement", "SwitchStatement", "DoWhileStatement", "DoStatement"}


CONDITION_BEARING_NODES = frozenset(
    {"IfStatement", "ForStatement", "WhileStatement", "DoWhileStatement", "DoStatement"}
)


def _edge_pairs(edges: Any) -> Iterator[Tuple[int, int]]:
    for edge in edges or []:
        if isinstance(edge, (list, tuple)) and len(edge) >= 2:
            try:
                yield int(edge[0]), int(edge[1])
            except Exception:
                continue
        elif isinstance(edge, dict):
            try:
                yield int(edge["src"]), int(edge["dst"])
            except Exception:
                continue


def _adjacency(edges: Any) -> Dict[int, List[int]]:
    adjacency: Dict[int, List[int]] = defaultdict(list)
    for src, dst in _edge_pairs(edges):
        adjacency[src].append(dst)
    return adjacency


def _parse_guard_edge(edge: Any) -> Optional[Tuple[int, int, int, Any]]:
    if isinstance(edge, dict):
        try:
            src = int(edge.get("src", -1))
            dst = int(edge.get("dst", -1))
            kind = int(edge.get("guard_kind", 0))
        except Exception:
            return None
        branch = edge.get("guard_branch", None)
    elif isinstance(edge, (list, tuple)) and len(edge) >= 3 and isinstance(edge[2], dict):
        try:
            src = int(edge[0])
            dst = int(edge[1])
        except Exception:
            return None
        feat = edge[2].get("feat", {})
        kind = int((feat.get("guard_kind") if isinstance(feat, dict) else 0) or 0)
        branch = None
    else:
        return None

    if kind not in GUARD_KINDS:
        return None
    return src, dst, kind, branch


def _condition_child_fallback(node_type: str, ast_node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    kids = (ast_node.get("children") or []) if isinstance(ast_node, dict) else []

    def child(index: int) -> Optional[Dict[str, Any]]:
        return kids[index] if len(kids) > index and isinstance(kids[index], dict) else None

    if node_type in {"IfStatement", "WhileStatement"}:
        return child(0)
    if node_type == "ForStatement":
        return child(1)
    if node_type in {"DoWhileStatement", "DoStatement"}:
        return next(
            (k for k in reversed(kids) if isinstance(k, dict) and k.get("nodeType") != "CompoundStatement"), None
        )
    return None


def _merge_aggregate(current: Optional[Dict[str, Any]], add: Dict[str, Any], kind: int) -> Dict[str, Any]:
    merged = current or {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0}
    merged["kind"] = merged.get("kind", 0) or kind
    try:
        merged["lower"] = max(int(merged.get("lower", 0)), int(add.get("lower", 0)))
        merged["upper"] = max(int(merged.get("upper", 0)), int(add.get("upper", 0)))
        merged["upper_const"] = max(float(merged.get("upper_const", 0.0)), float(add.get("upper_const", 0.0)))
    except Exception:
        pass
    return merged


class DFGExtractor:
    def __init__(self, ast_json: Dict[str, Any], ast_result: Dict[str, Any], sink_mode: str = "k1"):
        self.ast_json = ast_json
        self.ast_result = ast_result or {}

        self.ast_nodes = ast_result.get("nodes", [])
        self.ast_guard = ast_result.get("edges_ast_guard", [])

        self.sb_edges: Set[Tuple[int, int]] = set(_edge_pairs(ast_result.get("edges_ast_sb")))
        self.pointer_vars: Set[str] = self._collect_pointer_names(self.ast_json)

        self.sid2flat: Dict[int, Dict[str, Any]] = {}
        for _row in self.ast_nodes:
            try:
                _sid = int(_row.get("sid"))
            except Exception:
                continue
            self.sid2flat[_sid] = _row

        self.orig2sid: Dict[Any, int] = {}
        for _sid, _row in self.sid2flat.items():
            _oid = _row.get("orig_id")
            if _oid is not None:
                self.orig2sid.setdefault(_oid, _sid)
        self.sink_mode = sink_mode

        self.id2orig: Dict[int, Dict[str, Any]] = self._index_ast_by_id(self.ast_json)

        self.param_names: List[str] = self._collect_param_names(self.ast_json)

        self.nodes: List[Dict[str, Any]] = []
        self.edges_defuse: List[Tuple[int, int, Dict[str, Any]]] = []

        for n in self.ast_nodes:
            sid = int(n.get("sid"))
            code = n.get("code") or ""
            node_type = n.get("node_type") or ""

            self.nodes.append(
                {
                    "sid": sid,
                    "code": code,
                    "node_type_id": node_type,
                }
            )

        self.edges: List[Tuple[int, int, Dict[str, Any]]] = []

        self._sid2feat: Dict[int, Dict[str, Any]] = {
            int(r.get("sid")): (r.get("feat") or {}) for r in self.ast_nodes if "sid" in r
        }

    def run(self) -> Dict[str, Any]:
        self.guard_map = self._build_guard_map()
        acc = DefUseAccumulator(self.guard_map, debug_guard=getattr(self, "DEBUG_GUARD", False))
        for name in self.param_names:
            acc.seed_parameter(name)

        self.edges_defuse = acc.edges

        for row in self.nodes:
            self._process_statement(row, acc)

        return self._finalize(acc)

    def _process_statement(self, row: Dict[str, Any], acc: DefUseAccumulator) -> None:
        sid = row["sid"]
        code = row["code"]
        node_type = row["node_type_id"]

        acc.ensure_node(sid, node_type)
        acc.node_debug[sid]["code"] = code

        orig = self._orig_for_stmt(self._find_ast_row_by_sid(sid))
        scope = StatementScope()
        assign_rhs_has_call = False
        if node_type == "AssignmentExpression" and isinstance(orig, dict):
            rhs = self._nth_child(orig, 1)
            assign_rhs_has_call = isinstance(rhs, dict) and isinstance(self._find_first_call_node(rhs), dict)

        if (
            node_type in STATEMENT_CALL_NODE_TYPES
            and isinstance(orig, dict)
            and orig.get("nodeType") in ARGLIST_NODE_TYPES
        ):
            logger.debug("statement-level call node points only at an ArgList; handling call here: %s", code)
            self._handle_arglist_call(sid, orig, scope, acc)
            return

        if isinstance(orig, dict) and node_type not in CONTROL_NODES:
            if not assign_rhs_has_call:
                logger.debug("node_type not in CONTROL_NODES: %s", code)
                self._handle_nested_calls(sid, orig, scope, acc)
                if node_type in CALL_NODE_TYPES:
                    return

        if node_type in CONTROL_NODES and isinstance(orig, dict):
            self._handle_control_node(sid, node_type, orig, acc)
            return

        if node_type in SIMPLE_DECL_NODE_TYPES and isinstance(orig, dict):
            name = orig.get("name")
            if isinstance(name, str):
                acc.define(name, sid)
            return

        if node_type == "AssignmentExpression" and isinstance(orig, dict):
            self._handle_assignment(sid, code, orig, scope, acc)
            return

        if node_type in ARRAY_DECL_NODE_TYPES and isinstance(orig, dict):
            def_vars, uses = self._array_decl_by_ast(orig)
            for var, role in uses:
                acc.add_use_edge(var, role, sid)
            for var in def_vars:
                acc.define(var, sid)
            return

        if isinstance(orig, dict):
            self._handle_value_uses(sid, node_type, orig, scope, acc)

    def _handle_arglist_call(
        self, sid: int, arglist: Dict[str, Any], scope: StatementScope, acc: DefUseAccumulator
    ) -> None:
        name = self._callee_name_from_arglist(arglist)
        base = (name or "").lower()
        arg_nodes = arglist.get("children") or []

        self._record_call_arguments(sid, base, arg_nodes, scope, acc)
        self._apply_call_sink_flags(sid, base, arg_nodes, acc)

    def _handle_nested_calls(
        self, sid: int, orig: Dict[str, Any], scope: StatementScope, acc: DefUseAccumulator
    ) -> None:
        for name, arg_nodes in self._iter_calls_ast(orig):
            self._record_call_arguments(sid, name, arg_nodes, scope, acc)
            self._apply_call_sink_flags(sid, (name or "").lower(), arg_nodes, acc)

    def _record_call_arguments(
        self,
        sid: int,
        name: str,
        arg_nodes: List[Dict[str, Any]],
        scope: StatementScope,
        acc: DefUseAccumulator,
    ) -> None:
        for var, role in self._call_arg_uses_ast(name, arg_nodes):
            if role == "base":
                acc.add_use_edge(var, "base", sid)
                continue
            scope.used_by_call.add(var)
            acc.add_use_edge(var, role, sid)

        for var in self._call_write_effects_ast(name, arg_nodes):
            if var and var not in KEYWORDS:
                acc.define(var, sid)
                scope.excluded.add(var)

    def _apply_call_sink_flags(
        self, sid: int, base: str, arg_nodes: List[Dict[str, Any]], acc: DefUseAccumulator
    ) -> None:
        slots = dfg_sink_slots(base)
        dst_arg = self._arg_at(arg_nodes, slots.get("dst"))
        size_arg = self._arg_at(arg_nodes, slots.get("size"))
        dst_indexed = 1 if self._has_indexing(dst_arg, skip_sizeof=True) else 0
        size_txt = (size_arg.get("code") or "") if isinstance(size_arg, dict) else ""
        dst_names = set(self._idents_from_ast_node(dst_arg)) if isinstance(dst_arg, dict) else set()
        dst_full = self._fullname_from_expr(dst_arg) if isinstance(dst_arg, dict) else None
        if dst_full:
            dst_names.add(dst_full)

        linked = 0
        if size_txt and dst_names:
            linked = (
                1
                if any(
                    f"sizeof({dn})" in size_txt or f"sizeof(*{dn})" in size_txt or f"sizeof({dn}[0])" in size_txt
                    for dn in dst_names
                )
                else 0
            )

        size_txt_wo_sizeof = re.sub(r"\bsizeof\s*\([^)]*\)", "", size_txt)
        nonconst = 1 if (size_txt and re.search(r"[A-Za-z_]\w*", size_txt_wo_sizeof)) else 0
        if size_txt and "sizeof(" in size_txt:
            if not any(f"sizeof({dn})" in size_txt for dn in dst_names):
                nonconst = 1
            if dst_full and "." in dst_full and f"sizeof({dst_full.split('.')[0]})" in size_txt:
                nonconst = 1

        if base in UNBOUNDED:
            acc.node_feat[sid]["is_sink_call_unbounded"] = 1
            acc.node_feat[sid]["call_danger_unbounded"] = 1
            acc.raise_feat(sid, "call_dst_indexed", dst_indexed)
        elif base in BOUNDED:
            acc.node_feat[sid]["is_sink_call_bounded"] = 1
            acc.raise_feat(sid, "call_dst_indexed", dst_indexed)
            acc.raise_feat(sid, "call_len_linked_to_dst", linked)
            acc.raise_feat(sid, "call_size_nonconst", nonconst)

    def _handle_control_node(self, sid: int, node_type: str, orig: Dict[str, Any], acc: DefUseAccumulator) -> None:
        if self._get_condition_node(node_type, orig) is None:
            return

        if node_type == "ForStatement":
            for var in sorted(self._for_header_definitions(orig)):
                acc.define(var, sid)

        feat = acc.node_feat[sid]
        feat["is_buffer_access"] = 0
        feat["is_sink_assign"] = 0
        acc.clear_call_feats(sid)
        feat["def_count"] = len(acc.def_vars_by_sid[sid])
        feat["use_count"] = len(acc.use_vars_by_sid[sid])

    def _for_header_definitions(self, for_node: Dict[str, Any]) -> Set[str]:
        names: Set[str] = set()
        init = self._nth_child(for_node, 0)
        step = self._nth_child(for_node, 2)

        if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression":
            lhs = self._nth_child(init, 0)
            if isinstance(lhs, dict) and lhs.get("nodeType") == "Identifier":
                name = lhs.get("name")
                if isinstance(name, str) and name and name not in KEYWORDS:
                    names.add(name)

        if isinstance(step, dict):
            for token in self._idents_from_ast_node(step, skip_sizeof=True, skip_callee=True):
                if token and token not in KEYWORDS:
                    names.add(token)
        return names

    def _handle_assignment(
        self, sid: int, code: str, orig: Dict[str, Any], scope: StatementScope, acc: DefUseAccumulator
    ) -> None:
        lhs = self._nth_child(orig, 0)

        if isinstance(lhs, dict) and lhs.get("nodeType") == "ArraySubscriptExpression":
            index = self._nth_child(lhs, 1)
            if isinstance(index, dict):
                for var in self._idents_from_ast_node(index, skip_sizeof=True, skip_callee=True):
                    if var:
                        acc.add_use_edge(var, "index", sid)

        target = self._classify_assignment_target(lhs, code)
        def_vars, uses, is_buffer_access, is_sink = self._assignment_by_ast(orig, sid)

        if target.name and target.name not in KEYWORDS:
            if target.is_object_base:
                if target.name not in def_vars:
                    def_vars.append(target.name)
                if target.node_type in CONTAINER_WRITE_NODE_TYPES:
                    self._inject_container_guards(sid, lhs, target.node_type, acc)
                    acc.add_use_edge(target.name, "base", sid)
                uses = [(v, r) for (v, r) in uses if not (v == target.name and r == "base")]
            elif target.is_pointer_base:
                def_vars = [dv for dv in def_vars if dv != target.name]
                if (target.name, "base") not in uses:
                    uses.append((target.name, "base"))

        rhs = self._nth_child(orig, 1)
        rhs_call = self._find_first_call_node(rhs) if isinstance(rhs, dict) else None
        if isinstance(rhs_call, dict):
            uses = [(v, r) for (v, r) in uses if r != "value"]
        uses = [(v, r) for (v, r) in uses if not scope.skips(v)]

        for var, role in uses:
            acc.add_use_edge(var, role, sid)
        for var in def_vars:
            acc.define(var, sid)

        if isinstance(rhs_call, dict):
            call_sid = self.orig2sid.get(rhs_call.get("id"))
            if isinstance(call_sid, int) and self._sb_has(call_sid, sid):
                acc.add_return_value_edge(call_sid, sid)

        if is_buffer_access:
            acc.buffer_access_by_sid[sid] = 1
        if is_sink:
            acc.sink_assign_by_sid[sid] = 1

    def _classify_assignment_target(self, lhs: Optional[Dict[str, Any]], code: str) -> "AssignmentTarget":
        target = AssignmentTarget()
        if not isinstance(lhs, dict):
            return target

        target.node_type = lhs.get("nodeType")

        if target.node_type == "ArraySubscriptExpression":
            base_node = self._nth_child(lhs, 0)
            target.name = self._base_name(base_node)
            logger.debug("ArraySubscriptExpression code=%s lhs_base_name=%s", code, target.name)
            if isinstance(base_node, dict) and base_node.get("nodeType") == "PointerDereference":
                target.is_pointer_base = True
            logger.debug("ArraySubscriptExpression code=%s lhs_is_pointer_base=%s", code, target.is_pointer_base)
            if not target.is_pointer_base:
                if isinstance(base_node, dict) and base_node.get("nodeType") in {"Identifier", "MemberAccess"}:
                    target.is_object_base = True

        elif target.node_type == "PointerDereference":
            inner = self._nth_child(lhs, 0)
            target.name = self._base_name(inner)
            if (lhs.get("code") or "").strip().startswith("*"):
                target.is_pointer_base = True
            else:
                target.is_object_base = True

        elif target.node_type in {"Identifier", "MemberAccess"}:
            target.name = str(self._fullname_from_expr(lhs) or lhs.get("name") or "")
            target.is_object_base = True

        return target

    def _base_name(self, node: Optional[Dict[str, Any]]) -> str:
        if not isinstance(node, dict):
            return ""
        name = self._fullname_from_expr(node) or ""
        if not name and node.get("nodeType") == "Identifier":
            name = str(node.get("name") or "")
        return name

    def _inject_container_guards(
        self, sid: int, lhs: Optional[Dict[str, Any]], lhs_node_type: Optional[str], acc: DefUseAccumulator
    ) -> None:
        index_vars: List[str] = []
        if lhs_node_type == "ArraySubscriptExpression":
            index = self._nth_child(lhs, 1) if isinstance(lhs, dict) else None
            if isinstance(index, dict):
                index_vars = self._idents_from_ast_node(index, skip_sizeof=True, skip_callee=True)

        here = self.guard_map.get(sid, {})
        agg: Dict[str, Any] = {"kind": 0, "lower": 0, "upper": 0, "upper_const": 0.0}
        for var in index_vars or []:
            g = here.get(var) or here.get("*") or here.get("__agg__") or {}
            agg["lower"] |= int(g.get("lower", 0))
            agg["upper"] |= int(g.get("upper", 0))
            agg["upper_const"] = max(agg["upper_const"], float(g.get("upper_const", 0.0)))
            if not agg["kind"]:
                agg["kind"] = int(g.get("kind", 0))
        if not agg["kind"]:
            fallback = here.get("*") or here.get("__agg__") or {}
            agg["kind"] = int(fallback.get("kind", 0))
            agg["lower"] |= int(fallback.get("lower", 0))
            agg["upper"] |= int(fallback.get("upper", 0))
            agg["upper_const"] = max(agg["upper_const"], float(fallback.get("upper_const", 0.0)))

        slot = self.guard_map.setdefault(sid, {})
        slot["*"] = {
            "kind": agg["kind"],
            "lower": agg["lower"],
            "upper": agg["upper"],
            "upper_const": agg["upper_const"],
        }
        slot["__agg__"] = slot["*"]

    def _handle_value_uses(
        self, sid: int, node_type: str, orig: Dict[str, Any], scope: StatementScope, acc: DefUseAccumulator
    ) -> None:
        scan_node: Optional[Dict[str, Any]] = orig
        if node_type == "AssignmentExpression":
            rhs = self._nth_child(orig, 1)
            if isinstance(rhs, dict) and isinstance(self._find_first_call_node(rhs), dict):
                lhs = self._nth_child(orig, 0)
                scan_node = lhs if isinstance(lhs, dict) else orig
        for token in self._idents_from_ast_node(scan_node, skip_sizeof=True, skip_callee=True):
            if scope.skips(token):
                continue
            acc.add_use_edge(token, "value", sid)

    def _finalize(self, acc: DefUseAccumulator) -> Dict[str, Any]:
        deg_in, deg_out = acc.degrees([n["sid"] for n in self.nodes])

        out_nodes: List[Dict[str, Any]] = []
        for meta in self.nodes:
            sid = meta["sid"]
            node_type = meta["node_type_id"]
            acc.ensure_node(sid, node_type)

            use_vars = sorted(x for x in acc.use_vars_by_sid.get(sid, set()) if x and x != "<empty>")
            if node_type == "AssignmentExpression":
                use_vars = self._drop_rhs_call_idents(sid, use_vars)
            def_vars = sorted(x for x in acc.def_vars_by_sid.get(sid, set()) if x and x != "<empty>")
            feat = acc.node_feat[sid]
            feat["in_degree_dfg"] = deg_in.get(sid, 0)
            feat["out_degree_dfg"] = deg_out.get(sid, 0)
            feat["def_count"] = len(def_vars)
            feat["use_count"] = len(use_vars)
            feat["is_buffer_access"] = 1 if acc.buffer_access_by_sid.get(sid, 0) else 0
            feat["is_sink_assign"] = 1 if acc.sink_assign_by_sid.get(sid, 0) else 0

            if node_type == "AssignmentExpression":
                acc.clear_call_feats(sid)

            debug = acc.node_debug[sid]
            debug["code"] = meta["code"]
            debug["def_vars"] = def_vars
            debug["use_vars"] = use_vars

            out_nodes.append({"sid": sid, "feat": feat, "debug": debug})

        return {"nodes": out_nodes, "edges_dfg": acc.emitted_edges()}

    def _drop_rhs_call_idents(self, sid: int, use_vars: List[str]) -> List[str]:
        orig_id = (self.sid2flat.get(sid) or {}).get("orig_id")
        node = self.idmap.get(orig_id) if isinstance(orig_id, int) else None
        rhs = self._nth_child(node, 1) if isinstance(node, dict) else None
        if not isinstance(rhs, dict) or not isinstance(self._find_first_call_node(rhs), dict):
            return use_vars
        rhs_idents = set(self._idents_from_ast_node(rhs, skip_sizeof=True, skip_callee=True))
        return [x for x in use_vars if x not in rhs_idents]

    @staticmethod
    def _nth_child(node: Optional[Dict[str, Any]], index: int) -> Optional[Dict[str, Any]]:
        if not isinstance(node, dict):
            return None
        children = node.get("children") or []
        return children[index] if len(children) > index else None

    @staticmethod
    def _arg_at(arg_nodes: List[Dict[str, Any]], index: Optional[int]) -> Optional[Dict[str, Any]]:
        if index is None:
            return None
        return arg_nodes[index] if len(arg_nodes) > index else None

    def _find_ast_row_by_sid(self, sid: int) -> Dict[str, Any] | None:
        try:
            s = int(sid)
        except Exception:
            return None
        return self.sid2flat.get(s)

    def _orig_for_stmt(self, flat_row: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not isinstance(flat_row, dict):
            return None
        orig_id = flat_row.get("orig_id") if isinstance(flat_row.get("orig_id"), int) else None
        if orig_id is None:
            alt = flat_row.get("id")
            orig_id = alt if isinstance(alt, int) else None
        return self.id2orig.get(orig_id) if isinstance(orig_id, int) else None

    def _index_ast_by_id(self, node: Any) -> Dict[int, Dict[str, Any]]:
        out: Dict[int, Dict[str, Any]] = {}

        def walk(n: Any) -> None:
            if isinstance(n, dict):
                nid = n.get("id")
                if isinstance(nid, int):
                    out[nid] = n
                for c in n.get("children", []) or []:
                    walk(c)
            elif isinstance(n, list):
                for c in n:
                    walk(c)

        walk(node)
        return out

    def _collect_param_names(self, ast_json: Dict[str, Any]) -> List[str]:
        names: List[str] = []

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("nodeType") == "ParameterDeclaration":
                    nm = node.get("name")
                    if isinstance(nm, str) and nm:
                        names.append(nm)
                for ch in node.get("children", []) or []:
                    walk(ch)
            elif isinstance(node, list):
                for it in node:
                    walk(it)

        walk(ast_json)
        seen: Set[str] = set()
        out: List[str] = []
        for nm in names:
            if nm and nm != "<empty>" and nm not in seen:
                seen.add(nm)
                out.append(nm)
        return out

    def _get_condition_node(self, node_type: str, ast_node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(ast_node, dict):
            return None
        kids = ast_node.get("children") or []
        if node_type == "IfStatement":
            return kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
        if node_type == "ForStatement":
            return kids[1] if len(kids) >= 2 and isinstance(kids[1], dict) else None
        if node_type == "WhileStatement":
            return kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
        if node_type in {"DoWhileStatement", "DoStatement"}:
            for k in reversed(kids):
                if isinstance(k, dict) and k.get("nodeType") != "CompoundStatement":
                    return k
            return None
        return None

    def _fullname_from_expr(self, n: Any) -> Optional[str]:
        return fullname_from_expr(n, unwrap=unwrap_cast_paren)

    def _collect_pointer_names(self, ast_json: Dict[str, Any]) -> Set[str]:
        names: Set[str] = set()

        def walk(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("nodeType") == "PointerDeclaration":
                    nm = node.get("name")
                    if isinstance(nm, str) and nm:
                        names.add(nm)
                for ch in node.get("children") or []:
                    walk(ch)
            elif isinstance(node, list):
                for it in node:
                    walk(it)

        walk(ast_json)
        return names

    def _find_enclosing_call_for(self, node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(node, dict):
            return None
        target = node
        target_id = node.get("id") or node.get("orig_id")
        stack = [self.ast_json]
        while stack:
            n = stack.pop()
            if not isinstance(n, dict):
                continue
            if n.get("nodeType") in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
                for c in n.get("children") or []:
                    if not isinstance(c, dict):
                        continue
                    if c is target:
                        return n
                    cid = c.get("id") or c.get("orig_id")
                    if target_id is not None and cid is not None and cid == target_id:
                        return n
            stack.extend([c for c in (n.get("children") or []) if isinstance(c, dict)])
        return None

    def _callee_name_from_arglist(self, arglist_node: Dict[str, Any]) -> str:
        call = self._find_enclosing_call_for(arglist_node)
        if not isinstance(call, dict):
            return ""
        nm = call.get("name")
        if isinstance(nm, str) and nm:
            return nm
        kids = call.get("children") or []
        if kids and isinstance(kids[0], dict) and kids[0].get("nodeType") == "Identifier":
            nm2 = kids[0].get("name")
            if isinstance(nm2, str) and nm2:
                return nm2
        return ""

    def _iter_calls_ast(self, node: Dict[str, Any]) -> Iterator[Tuple[str, List[Dict[str, Any]]]]:
        def walk(n: Any) -> Iterator[Tuple[str, List[Dict[str, Any]]]]:
            if not isinstance(n, dict):
                return
            nt = n.get("nodeType")
            kids = n.get("children", []) or []

            if nt == "CallExpression":
                callee = kids[0] if kids else None
                fname = str(
                    (callee.get("name") if isinstance(callee, dict) and callee.get("nodeType") == "Identifier" else "")
                    or ""
                )
                args = [a for a in (kids[1:] if len(kids) > 1 else []) if isinstance(a, dict)]
                yield (fname, args)
                for a in args:
                    yield from walk(a)

            elif nt in {"StandardLibCall", "UserDefinedCall"}:
                fname = n.get("name") or ""
                plist = next(
                    (c for c in kids if isinstance(c, dict) and c.get("nodeType") in {"ParameterList", "ArgumentList"}),
                    None,
                )
                args = [
                    a for a in (plist.get("children", []) if isinstance(plist, dict) else []) if isinstance(a, dict)
                ]
                yield (str(fname or ""), args)
                for a in args:
                    yield from walk(a)
            else:
                for ch in kids:
                    yield from walk(ch)

        yield from walk(node)

    def _idents_from_ast_node(
        self, node: Dict[str, Any] | None, *, skip_sizeof: bool = True, skip_callee: bool = True
    ) -> List[str]:
        names: List[str] = []

        def _member_full_name(n: Optional[Dict[str, Any]]) -> str | None:
            if not isinstance(n, dict):
                return None
            nt = n.get("nodeType")
            if nt == "MemberAccess":
                kids = n.get("children") or []
                base = kids[0] if len(kids) > 0 else None
                field = kids[1] if len(kids) > 1 else None
                base_full = _member_full_name(base) or (
                    base.get("name") if isinstance(base, dict) and base.get("nodeType") == "Identifier" else None
                )
                field_name = (
                    field.get("name") if isinstance(field, dict) and field.get("nodeType") == "Identifier" else None
                )
                if base_full and field_name:
                    return f"{base_full}.{field_name}"
                return None
            elif nt == "Identifier":
                nm = n.get("name")
                return nm if isinstance(nm, str) and nm and nm not in KEYWORDS else None
            else:
                return None

        def _is_macro_const_call(n: Dict[str, Any]) -> bool:
            if not isinstance(n, dict) or n.get("nodeType") != "UserDefinedCall":
                return False

            lists = []
            stack = list(n.get("children") or [])
            while stack:
                z = stack.pop()
                if not isinstance(z, dict):
                    continue
                nt = z.get("nodeType")
                if nt in {"ParameterList", "ArgumentList"}:
                    lists.append(z)
                for c in z.get("children") or []:
                    if isinstance(c, dict):
                        stack.append(c)

            if not lists:
                return False

            def _has_compound(desc: Dict[str, Any]) -> bool:
                st = [desc]
                while st:
                    x = st.pop()
                    if not isinstance(x, dict):
                        continue
                    if x.get("nodeType") == "CompoundStatement":
                        return True
                    for cc in x.get("children") or []:
                        if isinstance(cc, dict):
                            st.append(cc)
                return False

            for pl in lists:
                if _has_compound(pl):
                    return True
            return False

        def walk(n: Any, under_sizeof: bool = False) -> None:
            if not isinstance(n, dict):
                return
            nt = n.get("nodeType")

            if nt == "SizeOfExpression":
                for c in n.get("children", []) or []:
                    walk(c, True if skip_sizeof else under_sizeof)
                return

            if nt in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
                if nt == "UserDefinedCall" and _is_macro_const_call(n):
                    return
                first = True
                for c in n.get("children", []) or []:
                    if first and skip_callee and isinstance(c, dict) and c.get("nodeType") == "Identifier":
                        first = False
                        continue
                    first = False
                    walk(c, under_sizeof)
                return

            if nt == "MemberAccess":
                if not under_sizeof:
                    full = _member_full_name(n)
                    if full and full not in KEYWORDS:
                        names.append(full)
                return

            if nt == "Identifier":
                nm = n.get("name")
                if isinstance(nm, str) and nm and nm not in KEYWORDS and not under_sizeof:
                    names.append(nm)

            for c in n.get("children", []) or []:
                walk(c, under_sizeof)

        walk(node, False)
        seen: Set[str] = set()
        out: List[str] = []
        for nm in names:
            if nm not in seen:
                seen.add(nm)
                out.append(nm)
        return out

    def _has_indexing(self, node: Dict[str, Any] | None, *, skip_sizeof: bool = True) -> bool:
        found = False

        def walk(n: Any, under_sizeof: bool = False) -> None:
            nonlocal found
            if found or not isinstance(n, dict):
                return
            nt = n.get("nodeType")
            if nt == "SizeOfExpression":
                for c in n.get("children", []) or []:
                    walk(c, True if skip_sizeof else under_sizeof)
                return
            if nt == "ArraySubscriptExpression":
                found = True
                return
            if nt in {"UnaryOperator", "UnaryExpression"} and n.get("operator") == "*":
                for ch in n.get("children", []) or []:
                    if (
                        isinstance(ch, dict)
                        and ch.get("nodeType") == "BinaryExpression"
                        and ch.get("operator") in {"+", "-"}
                    ):
                        found = True
                        return
            for c in n.get("children", []) or []:
                walk(c, under_sizeof)

        walk(node, False)
        return found

    def _is_decl_init_trick(self, sid: int, name: str, assign_node: Dict[str, Any]) -> bool:
        code = assign_node.get("code") or ""
        if not name or not code:
            return False
        pat_brace = r"^\s*" + re.escape(name) + r"\s*\[[^\]]+\]\s*=\s*\{"
        pat_str = r"^\s*" + re.escape(name) + r"\s*\[[^\]]+\]\s*=\s*\""
        if re.search(pat_brace, code) or re.search(pat_str, code):
            return True

        idx = None
        for i, n in enumerate(self.nodes):
            if n["sid"] == sid:
                idx = i
                break
        if idx is None:
            return False

        def _name_from_orig(row_sid: int) -> str:
            flat = self._find_ast_row_by_sid(row_sid)
            orig = self._orig_for_stmt(flat)
            if not isinstance(orig, dict):
                return ""
            nm = orig.get("name") if isinstance(orig.get("name"), str) else ""
            if not nm:
                for ch in orig.get("children", []) or []:
                    if isinstance(ch, dict) and ch.get("nodeType") == "Identifier":
                        n2 = ch.get("name")
                        if isinstance(n2, str) and n2:
                            return n2
            return nm or ""

        for j in (idx - 1, idx - 2):
            if j >= 0:
                nt = self.nodes[j]["node_type_id"]
                if nt in {"ArrayDeclaration", "ArraySizeAllocation"}:
                    if _name_from_orig(self.nodes[j]["sid"]) == name:
                        return True
        return False

    def _assignment_by_ast(
        self, assign_node: Dict[str, Any], cur_sid: int
    ) -> Tuple[List[str], List[Tuple[str, str]], int, int]:
        def_vars: List[str] = []
        uses: List[Tuple[str, str]] = []
        iba, is_sink = 0, 0
        kids = assign_node.get("children", []) or []
        lhs = kids[0] if len(kids) >= 1 else None
        rhs = kids[1] if len(kids) >= 2 else None
        base_name: Optional[str] = None

        def _lhs_textual_indexing(node: Dict[str, Any], name: str) -> Tuple[bool, bool]:
            code = (node.get("code") or "") if isinstance(node, dict) else ""
            if not code or not name:
                return (False, False)
            left = code.split("=", 1)[0]
            pattern = r"\b" + re.escape(name) + r"\s*\[([^\]]+)\]"
            m = re.search(pattern, left)
            if not m:
                return (False, False)
            idx_expr = m.group(1)
            idx_no_sizeof = re.sub(r"\bsizeof\s*\([^)]*\)", "", idx_expr)
            has_ident = bool(re.search(r"[A-Za-z_]\w*", idx_no_sizeof))
            return (True, has_ident)

        if isinstance(lhs, dict) and lhs.get("nodeType") == "ArraySubscriptExpression":
            base, index = (lhs.get("children") or [None, None])[:2]

            if isinstance(base, dict):
                base_full = self._fullname_from_expr(base)
                if base_full and base_full not in KEYWORDS:
                    uses.append((base_full, "base"))
            has_runtime_index = False
            if isinstance(index, dict):
                for t in self._idents_from_ast_node(index, skip_sizeof=False, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "index"))

                for t in self._idents_from_ast_node(index, skip_sizeof=True, skip_callee=True):
                    if t and t not in KEYWORDS:
                        has_runtime_index = True
                        break

            iba = 1
            is_sink = 1 if has_runtime_index else 0

        elif isinstance(lhs, dict) and lhs.get("nodeType") == "Identifier":
            base_name = lhs.get("name")
            if isinstance(base_name, str) and base_name and base_name not in KEYWORDS:
                def_vars.append(base_name)
                _has_idx, _idx_has_ident = _lhs_textual_indexing(assign_node, base_name)
                if _has_idx:
                    if not self._is_decl_init_trick(cur_sid, base_name, assign_node):
                        iba = 1
                        if _idx_has_ident:
                            is_sink = 1

        else:
            ids = self._idents_from_ast_node(lhs, skip_sizeof=True, skip_callee=True)
            if ids:
                def_vars.append(ids[0])

        rhs_index_vars: Set[str] = set()
        if isinstance(rhs, dict) and rhs.get("nodeType") == "ArraySubscriptExpression":
            rk = rhs.get("children") or []
            rhs_base = rk[0] if len(rk) > 0 else None
            rhs_index = rk[1] if len(rk) > 1 else None
            if isinstance(rhs_base, dict):
                rhs_base_full = self._fullname_from_expr(rhs_base)
                if rhs_base_full and rhs_base_full not in KEYWORDS:
                    uses.append((rhs_base_full, "base"))
            if isinstance(rhs_index, dict):
                for t in self._idents_from_ast_node(rhs_index, skip_sizeof=False, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "index"))
                        rhs_index_vars.add(t)

        return def_vars, uses, iba, is_sink

    def _array_decl_by_ast(self, decl: Dict[str, Any]) -> Tuple[List[str], List[Tuple[str, str]]]:
        def_vars: List[str] = []
        uses: List[Tuple[str, str]] = []
        nt = decl.get("nodeType")
        if nt == "ArrayDeclaration":
            nm = decl.get("name")
            if isinstance(nm, str) and nm and nm not in KEYWORDS:
                def_vars.append(nm)
            kids = decl.get("children") or []
            length = kids[0] if kids else None
            if isinstance(length, dict):
                for t in self._idents_from_ast_node(length, skip_sizeof=True, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "size"))
        elif nt == "ArraySizeAllocation":
            kids = decl.get("children") or []
            length = kids[0] if kids else None
            if isinstance(length, dict):
                for t in self._idents_from_ast_node(length, skip_sizeof=True, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "size"))

        return def_vars, uses

    def _call_arg_uses_ast(self, fname: str, arg_nodes: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        seen: Set[Tuple[str, str]] = set()
        index_vars: Set[str] = set()
        size_vars: Set[str] = set()
        base_vars: Set[str] = set()

        def _emit(name: str, role: str) -> None:
            if not name or name in KEYWORDS:
                return
            key = (name, role)
            if key not in seen:
                seen.add(key)
                out.append(key)

        low = (fname or "").lower()
        dst_pos = None
        size_pos = None
        if low in {"memcpy", "memmove", "strncpy"}:
            dst_pos, size_pos = 0, 2
        elif low in {"snprintf", "vsnprintf"}:
            dst_pos, size_pos = 0, 1
        elif low in {"fgets"}:
            dst_pos, size_pos = 0, 1
        elif low in {"read", "recv"}:
            dst_pos, size_pos = 1, 2
        elif low in {"getline"}:
            dst_pos, size_pos = 0, 1
        elif low in {"memset"}:
            dst_pos, size_pos = 0, 2
        elif low in {"connect"}:
            dst_pos, size_pos = None, 2

        for a in arg_nodes or []:
            if isinstance(a, dict) and a.get("nodeType") == "ArraySubscriptExpression":
                kids = a.get("children") or []
                idx_node = kids[1] if len(kids) > 1 else None
                if isinstance(idx_node, dict):
                    for t in self._idents_from_ast_node(idx_node, skip_sizeof=True, skip_callee=True):
                        _emit(t, "index")
                        index_vars.add(t)

        if size_pos is not None and 0 <= size_pos < len(arg_nodes or []):
            size_arg = arg_nodes[size_pos]
            if isinstance(size_arg, dict):
                for t in self._idents_from_ast_node(size_arg, skip_sizeof=True, skip_callee=True):
                    _emit(t, "size")
                    size_vars.add(t)

        if dst_pos is not None and 0 <= dst_pos < len(arg_nodes or []):
            dst_arg = arg_nodes[dst_pos]
            if isinstance(dst_arg, dict):
                for t in self._idents_from_ast_node(dst_arg, skip_sizeof=True, skip_callee=True):
                    logger.debug("%s: destination arg at position %s -> %s", fname, dst_pos, t)
                    _emit(t, "base")

                    base_vars.add(t)

        for i, a in enumerate(arg_nodes or []):
            if not isinstance(a, dict):
                continue
            if i == dst_pos or i == size_pos:
                continue
            for t in self._idents_from_ast_node(a, skip_sizeof=True, skip_callee=True):
                if t in index_vars or t in size_vars or t in base_vars:
                    continue
                _emit(t, "value")
        return out

    def _call_write_effects_ast(self, fname: str, arg_nodes: List[Dict[str, Any]]) -> List[str]:
        defs: List[str] = []

        def _emit(name: str | None) -> None:
            if name and name not in KEYWORDS and name not in defs:
                defs.append(name)

        def _first_ident(node: Dict[str, Any] | None) -> str:
            ids = self._idents_from_ast_node(node, skip_sizeof=True, skip_callee=True)
            return ids[0] if ids else ""

        def _dst_fullname(node: Dict[str, Any] | None) -> str:
            if not isinstance(node, dict):
                return ""
            core = unwrap_ast(node, strip_addr=True, strip_cast=True, strip_paren=True) or node
            full = self._fullname_from_expr(core)
            if full:
                return full
            return _first_ident(core)

        def _get_arg(idx: int) -> Dict[str, Any] | None:
            nodes = arg_nodes or []
            return nodes[idx] if 0 <= idx < len(nodes) else None

        low = (fname or "").lower()

        if low in {
            "memcpy",
            "memmove",
            "strcpy",
            "strcat",
            "strncpy",
            "snprintf",
            "sprintf",
            "vsnprintf",
            "vsprintf",
            "fgets",
            "gets",
            "memset",
        }:
            dst_idx = 0
            dst = _get_arg(dst_idx)
            _emit(_dst_fullname(dst))

        elif low in {"recv", "read", "getline"}:
            dst_idx = 1
            dst = _get_arg(dst_idx)
            _emit(_dst_fullname(dst))

        if low in {"scanf", "fscanf"}:
            for a in (arg_nodes or [])[1:]:
                nm = self._extract_address_of_ident(a)
                if nm:
                    _emit(nm)
                    continue
                if isinstance(a, dict) and a.get("nodeType") in {"UnaryOperator", "UnaryExpression"}:
                    kids = a.get("children") or []
                    if kids:
                        full = self._fullname_from_expr(kids[0])
                        _emit(full)

        return defs

    def _extract_address_of_ident(self, node: Dict[str, Any] | None) -> str:
        if not isinstance(node, dict):
            return ""
        nt = node.get("nodeType")
        if nt in {"UnaryOperator", "UnaryExpression"} and node.get("operator") == "&":
            for ch in node.get("children", []) or []:
                if isinstance(ch, dict) and ch.get("nodeType") == "Identifier":
                    nm = ch.get("name")
                    if isinstance(nm, str):
                        return nm
        ids = self._idents_from_ast_node(node, skip_sizeof=True, skip_callee=True)
        return ids[0] if ids else ""

    def _lower_from_for_init(self, for_node: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        res: Dict[str, Dict[str, Any]] = {}
        kids = for_node.get("children") or []
        init = kids[0] if len(kids) >= 1 else None
        if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression":
            lhs, rhs = (init.get("children") or [None, None])[:2]
            if (
                isinstance(lhs, dict)
                and lhs.get("nodeType") == "Identifier"
                and isinstance(rhs, dict)
                and rhs.get("nodeType") == "Literal"
            ):
                nm = lhs.get("name")
                val = rhs.get("value")
                if isinstance(nm, str) and isinstance(val, str) and val.isdigit():
                    if int(val) >= 0:
                        res[nm] = {"lower": 1, "upper": 0, "upper_const": 0.0}
        return res

    def _build_guard_map(self) -> Dict[int, Dict[str, Dict[str, Any]]]:
        ast_res = getattr(self, "ast_result", {}) or {}
        guard_edges = ast_res.get("edges_ast_guard") or getattr(self, "edges_ast_guard", []) or []
        parent_child = _adjacency(ast_res.get("edges_ast_pc") or getattr(self, "edges_ast_pc", []) or [])
        stmt_order = _adjacency(ast_res.get("edges_ast_sb") or getattr(self, "edges_ast_sb", []) or [])

        self._ensure_idmap(ast_res)
        condition_guards = self._condition_guards_by_statement(ast_res)
        gmap: Dict[int, Dict[str, Dict[str, Any]]] = defaultdict(dict)
        for edge in guard_edges:
            parsed = _parse_guard_edge(edge)
            if parsed is None:
                continue
            src_sid, block_head, kind, branch = parsed
            self._propagate_guard(gmap, condition_guards, src_sid, block_head, kind, branch, stmt_order, parent_child)
        return gmap

    def _ensure_idmap(self, ast_res: Dict[str, Any]) -> None:
        idmap = getattr(self, "idmap", None)
        if isinstance(idmap, dict) and idmap:
            return

        root = (
            getattr(self, "ast_json", None)
            or ast_res.get("ast_json")
            or getattr(self, "ast", None)
            or ast_res.get("ast")
        )
        built: Dict[int, Dict[str, Any]] = {}
        if isinstance(root, dict):

            def walk(node: Any) -> None:
                if isinstance(node, dict):
                    nid = node.get("id")
                    if isinstance(nid, int):
                        built[nid] = node
                    for child in node.get("children") or []:
                        walk(child)
                elif isinstance(node, list):
                    for child in node:
                        walk(child)

            walk(root)
        self.idmap = built

    def _orig_ast_for_sid(self, sid: Any, ast_nodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if isinstance(self.sid2flat, dict):
            oid = (self.sid2flat.get(sid) or {}).get("orig_id")
            if isinstance(oid, int):
                return self.idmap.get(oid)
        for rows in (ast_nodes, self.nodes or []):
            for row in rows:
                try:
                    if int(row.get("sid", -1) or -1) != int(sid or -1):
                        continue
                except Exception:
                    continue
                oid = row.get("orig_id")
                if isinstance(oid, int):
                    return self.idmap.get(oid)
        return None

    def _condition_guards_by_statement(self, ast_res: Dict[str, Any]) -> Dict[int, Dict[str, Dict[str, Any]]]:
        ast_nodes = ast_res.get("nodes") or []
        out: Dict[int, Dict[str, Dict[str, Any]]] = {}

        for row in self.nodes or []:
            sid = row.get("sid")
            node_type = row.get("node_type_id") or row.get("node_type")
            if not isinstance(sid, int) or node_type not in CONDITION_BEARING_NODES:
                continue
            ast_node = self._orig_ast_for_sid(sid, ast_nodes)
            if not isinstance(ast_node, dict):
                continue

            try:
                cond_ast = self._get_condition_node(node_type, ast_node)
            except Exception:
                cond_ast = _condition_child_fallback(node_type, ast_node)

            parsed: Dict[str, Any] = {}
            if cond_ast is not None:
                try:
                    parsed = guards_from_condition_ast(cond_ast) or {}
                except Exception:
                    parsed = {}

            guards: Dict[str, Dict[str, Any]] = {}
            for var, g in parsed.items() if isinstance(parsed, dict) else []:
                if not var:
                    continue
                try:
                    guards[var] = {
                        "lower": int(g.get("lower", 0)),
                        "upper": int(g.get("upper", 0)),
                        "upper_const": float(g.get("upper_const", 0.0)),
                    }
                except Exception:
                    guards[var] = {"lower": 0, "upper": 0, "upper_const": 0.0}

            if node_type == "ForStatement":
                for var, g in (guards_from_for_header(ast_node) or {}).items():
                    entry = guards.setdefault(var, {"lower": 0, "upper": 0, "upper_const": 0.0})
                    entry["lower"] = max(entry["lower"], int(g.get("lower", 0)))

            out[sid] = guards
        return out

    def _propagate_guard(
        self,
        gmap: Dict[int, Dict[str, Dict[str, Any]]],
        condition_guards: Dict[int, Dict[str, Dict[str, Any]]],
        src_sid: int,
        block_head: int,
        kind: int,
        branch: Any,
        stmt_order: Dict[int, List[int]],
        parent_child: Dict[int, List[int]],
    ) -> None:
        if kind == GUARD_KIND_IF:
            var_guards = (condition_guards.get(src_sid, {}) or {}) if branch == 0 else {}
        elif kind == GUARD_KIND_LOOP:
            var_guards = condition_guards.get(src_sid, {}) or {}
        else:
            var_guards = {}

        aggregate: Dict[str, Any] = {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0}
        for g in var_guards.values():
            try:
                aggregate["lower"] |= int(g.get("lower", 0))
                aggregate["upper"] |= int(g.get("upper", 0))
                aggregate["upper_const"] = max(aggregate["upper_const"], float(g.get("upper_const", 0.0)))
            except Exception:
                pass

        queue: deque[int] = deque([block_head])
        seen: Set[int] = set()
        while queue:
            sid = queue.popleft()
            if sid in seen:
                continue
            seen.add(sid)

            entry = gmap.setdefault(sid, {})
            for var, g in var_guards.items():
                cur = entry.get(var, {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0})
                if not cur.get("kind"):
                    cur["kind"] = kind
                try:
                    cur["lower"] |= int(g.get("lower", 0))
                    cur["upper"] |= int(g.get("upper", 0))
                    cur["upper_const"] = max(float(cur.get("upper_const", 0.0)), float(g.get("upper_const", 0.0)))
                except Exception:
                    pass
                entry[var] = cur

            entry["*"] = _merge_aggregate(entry.get("*"), aggregate, kind)
            entry["__agg__"] = entry["*"]

            for successor in stmt_order.get(sid, []):
                if successor not in seen:
                    queue.append(successor)
            for successor in parent_child.get(sid, []):
                if successor not in seen:
                    queue.append(successor)

    def _guard_ctx_by_sid(self, sid: int) -> Dict[str, Any]:
        f = self._sid2feat.get(int(sid), {}) or {}
        kind = 2 if f.get("in_loop", 0) else (1 if f.get("ctx_guard_strength", 0) else 0)
        s = int(f.get("ctx_guard_strength", 0) or 0)
        return {
            "kind": kind,
            "lower": 1 if s in (1, 3) else 0,
            "upper": 1 if s in (2, 3) else 0,
            "upper_const": float(f.get("ctx_upper_bound_norm", 0.0) or 0.0),
        }

    def _find_first_call_node(self, node: Any) -> Optional[Dict[str, Any]]:
        def walk(n: Any) -> Optional[Dict[str, Any]]:
            if not isinstance(n, dict):
                return None
            if n.get("nodeType") in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
                return n
            for ch in n.get("children") or []:
                r = walk(ch)
                if r is not None:
                    return r
            return None

        return walk(node)

    def _sb_has(self, prev_sid: int, next_sid: int) -> bool:
        try:
            return (int(prev_sid), int(next_sid)) in self.sb_edges
        except Exception:
            return False
