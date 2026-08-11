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


#: Control statements that carry a condition worth reading bounds from. Excludes
#: SwitchStatement, which contributes a guard kind but no per-variable bounds --
#: which is why this is not CONTROL_NODES.
CONDITION_BEARING_NODES = frozenset(
    {"IfStatement", "ForStatement", "WhileStatement", "DoWhileStatement", "DoStatement"}
)


def _edge_pairs(edges: Any) -> Iterator[Tuple[int, int]]:
    """(src, dst) for every well-formed edge, skipping any that will not parse.

    Edges arrive either as ``[src, dst, ...]`` or as ``{"src":, "dst":}``; three
    places used to spell this out. Malformed entries are skipped rather than
    raised, as all three did.
    """
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
    """Successor lists keyed by source node."""
    adjacency: Dict[int, List[int]] = defaultdict(list)
    for src, dst in _edge_pairs(edges):
        adjacency[src].append(dst)
    return adjacency


def _parse_guard_edge(edge: Any) -> Optional[Tuple[int, int, int, Any]]:
    """``(src_sid, block_head, kind, branch)`` from a guard edge, or None to skip it.

    The list form carries its kind under ``[2]["feat"]`` and has no branch, so an
    ``if`` edge in that shape never gets then-branch guards.
    """
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
    """Where the condition sits among a control statement's children.

    Only used if :meth:`DFGExtractor._get_condition_node` raises.
    """
    kids = (ast_node.get("children") or []) if isinstance(ast_node, dict) else []

    def child(index: int) -> Optional[Dict[str, Any]]:
        return kids[index] if len(kids) > index and isinstance(kids[index], dict) else None

    if node_type in {"IfStatement", "WhileStatement"}:
        return child(0)
    if node_type == "ForStatement":
        return child(1)
    if node_type in {"DoWhileStatement", "DoStatement"}:
        # the last child that is not the body
        return next(
            (k for k in reversed(kids) if isinstance(k, dict) and k.get("nodeType") != "CompoundStatement"), None
        )
    return None


def _merge_aggregate(current: Optional[Dict[str, Any]], add: Dict[str, Any], kind: int) -> Dict[str, Any]:
    """Merge aggregate guard evidence, keeping the first kind seen and the strongest bounds."""
    merged = current or {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0}
    merged["kind"] = merged.get("kind", 0) or kind
    try:
        merged["lower"] = max(int(merged.get("lower", 0)), int(add.get("lower", 0)))
        merged["upper"] = max(int(merged.get("upper", 0)), int(add.get("upper", 0)))
        merged["upper_const"] = max(float(merged.get("upper_const", 0.0)), float(add.get("upper_const", 0.0)))
    except Exception:
        pass
    return merged


# ------------------------------
# DFG Extractor V1.9
# ------------------------------
class DFGExtractor:
    def __init__(self, ast_json: Dict[str, Any], ast_result: Dict[str, Any], sink_mode: str = "k1"):
        self.ast_json = ast_json
        self.ast_result = ast_result or {}

        self.ast_nodes = ast_result.get("nodes", [])
        self.ast_guard = ast_result.get("edges_ast_guard", [])

        # Statement-order edges as a lookup set, for _sb_has(). This was never
        # assigned: _sb_has read `self.sb_edges`, the resulting AttributeError
        # was swallowed by its `except Exception`, and it therefore always
        # returned False -- silently suppressing the call->assignment
        # return-value edge it guards.
        self.sb_edges: Set[Tuple[int, int]] = set(_edge_pairs(ast_result.get("edges_ast_sb")))
        self.pointer_vars: Set[str] = self._collect_pointer_names(self.ast_json)  # Collect PointerDeclaration

        # map: sid -> flat AST row (to fetch orig_id etc.)
        self.sid2flat: Dict[int, Dict[str, Any]] = {}
        for _row in self.ast_nodes:
            try:
                _sid = int(_row.get("sid"))
            except Exception:
                continue
            self.sid2flat[_sid] = _row

        # Reverse index: original AST node id -> statement sid. Referenced by
        # the call->assignment edge below as `self.orig2sid` but never built,
        # so that path raised AttributeError whenever it was reached.
        self.orig2sid: Dict[Any, int] = {}
        for _sid, _row in self.sid2flat.items():
            _oid = _row.get("orig_id")
            if _oid is not None:
                self.orig2sid.setdefault(_oid, _sid)
        self.sink_mode = sink_mode

        # Original AST index (id -> node)
        self.id2orig: Dict[int, Dict[str, Any]] = self._index_ast_by_id(self.ast_json)

        # Parameter list
        self.param_names: List[str] = self._collect_param_names(self.ast_json)

        # Result container
        self.nodes: List[Dict[str, Any]] = []  # DFG nodes (features)
        self.edges_defuse: List[Tuple[int, int, Dict[str, Any]]] = []  # <- flat Def->Use (for collection)

        # Initialize DFG nodes (share sid). Debug fields are synchronized in run()
        for n in self.ast_nodes:
            sid = int(n.get("sid"))
            code = n.get("code") or ""
            node_type = n.get("node_type") or ""

            self.nodes.append(
                {
                    "sid": sid,
                    "code": code,
                    "node_type_id": node_type,
                    # These fields will be overwritten in run() with actual DEF/USE/degree
                }
            )

        # Final output edges (split into 'feat'/'debug') are assembled in run() into self.edges
        self.edges: List[Tuple[int, int, Dict[str, Any]]] = []

        # Cache (sid -> feat) for guard injection based on dst SID
        self._sid2feat: Dict[int, Dict[str, Any]] = {
            int(r.get("sid")): (r.get("feat") or {}) for r in self.ast_nodes if "sid" in r
        }

    # ------------------------------
    # Public: build edges + finalize node features
    # ------------------------------
    def run(self) -> Dict[str, Any]:
        """Build the def-use edges and finalize per-node features.

        One pass over the flattened statement list. Each statement is dispatched
        to the handler for its node family; the handlers share the bookkeeping in
        :class:`DefUseAccumulator` rather than closing over locals.
        """
        self.guard_map = self._build_guard_map()
        acc = DefUseAccumulator(self.guard_map, debug_guard=getattr(self, "DEBUG_GUARD", False))
        for name in self.param_names:
            acc.seed_parameter(name)

        # Kept as an attribute because the class has always exposed it.
        self.edges_defuse = acc.edges

        for row in self.nodes:
            self._process_statement(row, acc)

        return self._finalize(acc)

    def _process_statement(self, row: Dict[str, Any], acc: DefUseAccumulator) -> None:
        """Route one statement to the handler for its node family.

        The order matters and mirrors what the single loop did: a call consumes
        the statement before the generic scans get to it, and control nodes never
        reach the value scan.
        """
        sid = row["sid"]
        code = row["code"]
        node_type = row["node_type_id"]

        acc.ensure_node(sid, node_type)
        acc.node_debug[sid]["code"] = code

        orig = self._orig_for_stmt(self._find_ast_row_by_sid(sid))
        scope = StatementScope()

        # When an assignment's RHS contains a call, the split-out call node owns
        # that call's argument uses, write effects and sink bits -- not this
        # assignment node. Decided up front because it suppresses the scan below.
        assign_rhs_has_call = False
        if node_type == "AssignmentExpression" and isinstance(orig, dict):
            rhs = self._nth_child(orig, 1)
            assign_rhs_has_call = isinstance(rhs, dict) and isinstance(self._find_first_call_node(rhs), dict)

        # (0) A statement-level call node whose orig points only at an argument
        # list. The call is handled here in full, including index-role uses.
        if (
            node_type in STATEMENT_CALL_NODE_TYPES
            and isinstance(orig, dict)
            and orig.get("nodeType") in ARGLIST_NODE_TYPES
        ):
            logger.debug("statement-level call node points only at an ArgList; handling call here: %s", code)
            self._handle_arglist_call(sid, orig, scope, acc)
            return

        # (0b) Calls nested inside some other statement.
        if isinstance(orig, dict) and node_type not in CONTROL_NODES:
            if not assign_rhs_has_call:
                logger.debug("node_type not in CONTROL_NODES: %s", code)
                self._handle_nested_calls(sid, orig, scope, acc)
                # A call statement is finished; do not also value-scan it.
                if node_type in CALL_NODE_TYPES:
                    return

        # (1) Control node: seed any header definitions, then stop.
        if node_type in CONTROL_NODES and isinstance(orig, dict):
            self._handle_control_node(sid, node_type, orig, acc)
            return

        # (2) Declaration.
        if node_type in SIMPLE_DECL_NODE_TYPES and isinstance(orig, dict):
            name = orig.get("name")
            if isinstance(name, str):
                acc.define(name, sid)
            return

        # (3) Assignment.
        if node_type == "AssignmentExpression" and isinstance(orig, dict):
            self._handle_assignment(sid, code, orig, scope, acc)
            return

        # (4) Array declaration / sized allocation.
        if node_type in ARRAY_DECL_NODE_TYPES and isinstance(orig, dict):
            def_vars, uses = self._array_decl_by_ast(orig)
            for var, role in uses:
                acc.add_use_edge(var, role, sid)
            for var in def_vars:
                acc.define(var, sid)
            return

        # (5) Anything else: every identifier is a value USE.
        if isinstance(orig, dict):
            self._handle_value_uses(sid, node_type, orig, scope, acc)

    # ------------------------------
    # Statement handlers
    # ------------------------------

    def _handle_arglist_call(
        self, sid: int, arglist: Dict[str, Any], scope: StatementScope, acc: DefUseAccumulator
    ) -> None:
        """A call whose statement node points only at its argument list.

        Note this passes the *lowercased* name to the argument readers, where
        :meth:`_handle_nested_calls` passes the name as written. The two paths
        have always differed here.
        """
        name = self._callee_name_from_arglist(arglist)
        base = (name or "").lower()
        arg_nodes = arglist.get("children") or []

        self._record_call_arguments(sid, base, arg_nodes, scope, acc)
        self._apply_call_sink_flags(sid, base, arg_nodes, acc)

    def _handle_nested_calls(
        self, sid: int, orig: Dict[str, Any], scope: StatementScope, acc: DefUseAccumulator
    ) -> None:
        """Every call found inside a statement that is not itself a bare call."""
        for name, arg_nodes in self._iter_calls_ast(orig):
            # The name as written goes to the argument readers, the lowercased
            # one to the sink tables. See _handle_arglist_call.
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
        """Argument USEs by role, then the definitions the call writes through."""
        for var, role in self._call_arg_uses_ast(name, arg_nodes):
            if role == "base":
                acc.add_use_edge(var, "base", sid)  # flow_id = 4
                continue
            scope.used_by_call.add(var)
            acc.add_use_edge(var, role, sid)

        for var in self._call_write_effects_ast(name, arg_nodes):
            if var and var not in KEYWORDS:
                acc.define(var, sid)
                scope.excluded.add(var)  # the destination is not also a token USE

    def _apply_call_sink_flags(
        self, sid: int, base: str, arg_nodes: List[Dict[str, Any]], acc: DefUseAccumulator
    ) -> None:
        """Set the sink-evidence bits for a call to ``base``.

        Answers three questions about the destination buffer and its size
        argument: is the destination indexed, is the size tied to the
        destination's own ``sizeof``, and is the size non-constant.
        """
        slots = dfg_sink_slots(base)
        dst_arg = self._arg_at(arg_nodes, slots.get("dst"))
        size_arg = self._arg_at(arg_nodes, slots.get("size"))

        dst_indexed = 1 if self._has_indexing(dst_arg, skip_sizeof=True) else 0

        size_txt = (size_arg.get("code") or "") if isinstance(size_arg, dict) else ""
        dst_names = set(self._idents_from_ast_node(dst_arg)) if isinstance(dst_arg, dict) else set()
        dst_full = self._fullname_from_expr(dst_arg) if isinstance(dst_arg, dict) else None
        if dst_full:
            dst_names.add(dst_full)

        # len-linked: the size is sizeof the destination itself.
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

        # A size equal to the *declared* length is deliberately not len-linked;
        # the block that used to compute and discard that comparison is gone.

        size_txt_wo_sizeof = re.sub(r"\bsizeof\s*\([^)]*\)", "", size_txt)
        nonconst = 1 if (size_txt and re.search(r"[A-Za-z_]\w*", size_txt_wo_sizeof)) else 0
        if size_txt and "sizeof(" in size_txt:
            # A sizeof that is not the destination's does not bound it.
            if not any(f"sizeof({dn})" in size_txt for dn in dst_names):
                nonconst = 1
            # Destination is base.field but the size is sizeof(base).
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
        """A control structure defines only what its header assigns."""
        if self._get_condition_node(node_type, orig) is None:
            return

        if node_type == "ForStatement":
            for var in sorted(self._for_header_definitions(orig)):
                acc.define(var, sid)

        # A control node is not a call and does not write a buffer.
        feat = acc.node_feat[sid]
        feat["is_buffer_access"] = 0
        feat["is_sink_assign"] = 0
        acc.clear_call_feats(sid)
        feat["def_count"] = len(acc.def_vars_by_sid[sid])
        feat["use_count"] = len(acc.use_vars_by_sid[sid])

    def _for_header_definitions(self, for_node: Dict[str, Any]) -> Set[str]:
        """Variables a ``for`` header assigns: the init target and anything the step touches."""
        names: Set[str] = set()
        init = self._nth_child(for_node, 0)
        step = self._nth_child(for_node, 2)

        # init: i = <expr> defines i
        if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression":
            lhs = self._nth_child(init, 0)
            if isinstance(lhs, dict) and lhs.get("nodeType") == "Identifier":
                name = lhs.get("name")
                if isinstance(name, str) and name and name not in KEYWORDS:
                    names.add(name)

        # step: ++i, i++, i += k all define i
        if isinstance(step, dict):
            for token in self._idents_from_ast_node(step, skip_sizeof=True, skip_callee=True):
                if token and token not in KEYWORDS:
                    names.add(token)
        return names

    def _handle_assignment(
        self, sid: int, code: str, orig: Dict[str, Any], scope: StatementScope, acc: DefUseAccumulator
    ) -> None:
        """An assignment: what it writes, what it reads, and how it reaches the target."""
        lhs = self._nth_child(orig, 0)

        # An index expression on the left is read before the write: buf[i] = x
        # uses i. Done first so the index USE precedes the base's definition.
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
                # Writing the object itself: keep the definition, drop the base USE.
                if target.name not in def_vars:
                    def_vars.append(target.name)
                if target.node_type in CONTAINER_WRITE_NODE_TYPES:
                    self._inject_container_guards(sid, lhs, target.node_type, acc)
                    # Before the definition is recorded, so var_key names the
                    # previous definition rather than this statement.
                    acc.add_use_edge(target.name, "base", sid)
                uses = [(v, r) for (v, r) in uses if not (v == target.name and r == "base")]
            elif target.is_pointer_base:
                # Writing *through* a pointer defines the pointee, not the pointer.
                def_vars = [dv for dv in def_vars if dv != target.name]
                if (target.name, "base") not in uses:
                    uses.append((target.name, "base"))

        # If the RHS is a call, its value uses belong to the split call node.
        rhs = self._nth_child(orig, 1)
        rhs_call = self._find_first_call_node(rhs) if isinstance(rhs, dict) else None
        if isinstance(rhs_call, dict):
            uses = [(v, r) for (v, r) in uses if r != "value"]
        uses = [(v, r) for (v, r) in uses if not scope.skips(v)]

        for var, role in uses:
            acc.add_use_edge(var, role, sid)
        for var in def_vars:
            acc.define(var, sid)

        # x = f(...): carry f's return value into this statement.
        if isinstance(rhs_call, dict):
            call_sid = self.orig2sid.get(rhs_call.get("id"))
            if isinstance(call_sid, int) and self._sb_has(call_sid, sid):
                acc.add_return_value_edge(call_sid, sid)

        if is_buffer_access:
            acc.buffer_access_by_sid[sid] = 1
        if is_sink:
            acc.sink_assign_by_sid[sid] = 1

    def _classify_assignment_target(self, lhs: Optional[Dict[str, Any]], code: str) -> "AssignmentTarget":
        """What the left-hand side names, and whether the write lands on it or through it."""
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
            # Only a leading '*' is a real dereference; the front end also wraps
            # a plain `data = ...` in this node type.
            if (lhs.get("code") or "").strip().startswith("*"):
                target.is_pointer_base = True
            else:
                target.is_object_base = True

        elif target.node_type in {"Identifier", "MemberAccess"}:
            target.name = str(self._fullname_from_expr(lhs) or lhs.get("name") or "")
            target.is_object_base = True

        return target

    def _base_name(self, node: Optional[Dict[str, Any]]) -> str:
        """Name of an lvalue, falling back to a plain identifier's name."""
        if not isinstance(node, dict):
            return ""
        name = self._fullname_from_expr(node) or ""
        if not name and node.get("nodeType") == "Identifier":
            name = str(node.get("name") or "")
        return name

    def _inject_container_guards(
        self, sid: int, lhs: Optional[Dict[str, Any]], lhs_node_type: Optional[str], acc: DefUseAccumulator
    ) -> None:
        """Synthesize a fallback guard entry for a write into a container.

        ``buf[i] = x`` is only as safe as the checks on ``i``, so the index
        variables' guard evidence is merged and parked under the ``*`` and
        ``__agg__`` keys for this statement, where :meth:`add_use_edge` will find
        it when no variable-specific entry exists.
        """
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
        # Both keys intentionally reference one dict, as before.
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
        """Fallback: every identifier in the statement is a value USE."""
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

    # ------------------------------
    # Output
    # ------------------------------

    def _finalize(self, acc: DefUseAccumulator) -> Dict[str, Any]:
        """Fold degrees and counts into the node features and emit the graph."""
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
            feat["use_count"] = len(use_vars)  # base role excluded
            feat["is_buffer_access"] = 1 if acc.buffer_access_by_sid.get(sid, 0) else 0
            feat["is_sink_assign"] = 1 if acc.sink_assign_by_sid.get(sid, 0) else 0

            # An assignment is call-neutral even when a call sits in its RHS.
            if node_type == "AssignmentExpression":
                acc.clear_call_feats(sid)

            debug = acc.node_debug[sid]
            debug["code"] = meta["code"]
            debug["def_vars"] = def_vars
            debug["use_vars"] = use_vars

            out_nodes.append({"sid": sid, "feat": feat, "debug": debug})

        return {"nodes": out_nodes, "edges_dfg": acc.emitted_edges()}

    def _drop_rhs_call_idents(self, sid: int, use_vars: List[str]) -> List[str]:
        """Remove identifiers that belong to a call in this assignment's RHS.

        They are counted against the split-out call node instead, so leaving them
        here would double-count them.
        """
        orig_id = (self.sid2flat.get(sid) or {}).get("orig_id")
        node = self.idmap.get(orig_id) if isinstance(orig_id, int) else None
        rhs = self._nth_child(node, 1) if isinstance(node, dict) else None
        if not isinstance(rhs, dict) or not isinstance(self._find_first_call_node(rhs), dict):
            return use_vars
        rhs_idents = set(self._idents_from_ast_node(rhs, skip_sizeof=True, skip_callee=True))
        return [x for x in use_vars if x not in rhs_idents]

    # ------------------------------
    # Small shared readers
    # ------------------------------

    @staticmethod
    def _nth_child(node: Optional[Dict[str, Any]], index: int) -> Optional[Dict[str, Any]]:
        """``node``'s child at ``index``, or None."""
        if not isinstance(node, dict):
            return None
        children = node.get("children") or []
        return children[index] if len(children) > index else None

    @staticmethod
    def _arg_at(arg_nodes: List[Dict[str, Any]], index: Optional[int]) -> Optional[Dict[str, Any]]:
        """The argument at ``index``, or None when there is no such slot."""
        if index is None:
            return None
        return arg_nodes[index] if len(arg_nodes) > index else None

    # ------------------------------
    # AST helpers / schema-based visitors
    # ------------------------------
    def _find_ast_row_by_sid(self, sid: int) -> Dict[str, Any] | None:
        """Return flattened AST row by sid (has orig_id/id/code/node_type_id)."""
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
            # Some pipelines may preserve id even in flattened rows
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
        # 순서보존 dedupe
        seen: Set[str] = set()
        out: List[str] = []
        for nm in names:
            # Exclude empty strings/placeholders + remove duplicates
            if nm and nm != "<empty>" and nm not in seen:
                seen.add(nm)
                out.append(nm)
        return out

    def _get_condition_node(self, node_type: str, ast_node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Returns the 'condition expression' subtree from control statement AST nodes.
        - If: children[0]
        - For: children[1]   <- (init, cond, inc)
        - While: children[0]
        - Do/DoWhile: Last non-CompoundStatement
        """
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
        """The identifier this expression names. See :func:`ssat.nodes.fullname_from_expr`.

        The peeling strategy is bound here because the two extractors do not
        agree on it; this one keeps dfg's, which also peels parentheses and
        takes a cast's first child.
        """
        return fullname_from_expr(n, unwrap=unwrap_cast_paren)

    # ------------------------------
    # PointerDeclaration 수집
    # ------------------------------
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
        """ParameterList/ArgumentList 노드의 상위 CallExpression을 찾아 반환."""
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
        """ParameterList/ArgumentList에서 callee 이름을 AST의 name으로 가져옴.
        CallExpression.name이 없으면 첫 자식 Identifier.name 사용."""
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
                # ParameterList / ArgumentList 중 하나를 찾아 인자들 추출
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
        """
        식별자(이름) 추출기.
        - Identifier: 그대로 수집
        - MemberAccess: 'base.field[.subfield...]' 1토큰
        - sizeof(...) 내부 식별자는 기본 스킵
        - CallExpression의 첫 자식(callee) 기본 스킵
        - **매크로 상수(UserDefinedCall→ParameterList/ArgumentList→…→Literal)는 식별자로 취급하지 않음**
        - 순서 보존 dedupe
        """
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
            """
            UserDefinedCall 하위에 존재하는 (ParameterList|ArgumentList)들 중
            하나라도 CompoundStatement를 후손으로 가지면 '매크로-상수 호출'로 판단한다.

            예) StandardLibCall(inet_addr)
                └─ ParameterList
                └─ UserDefinedCall(IP_ADDRESS)
                    └─ ParameterList
                        └─ CompoundStatement
                            └─ Literal "127.0.0.1"
            """
            if not isinstance(n, dict) or n.get("nodeType") != "UserDefinedCall":
                return False

            # 1) UDC 하위의 모든 (ParameterList|ArgumentList)를 수집
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

            # 2) 각 리스트의 후손에 CompoundStatement가 있는지 탐색
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

            # sizeof(...) 내부는 USE로 세지 않음
            if nt == "SizeOfExpression":
                for c in n.get("children", []) or []:
                    walk(c, True if skip_sizeof else under_sizeof)
                return

            # 호출 노드
            if nt in {"StandardLibCall", "UserDefinedCall", "CallExpression"}:
                # 매크로 상수 의사 호출이면 통째로 무시
                if nt == "UserDefinedCall" and _is_macro_const_call(n):
                    return
                # 첫 자식(callee) 스킵
                first = True
                for c in n.get("children", []) or []:
                    if first and skip_callee and isinstance(c, dict) and c.get("nodeType") == "Identifier":
                        first = False
                        continue
                    first = False
                    walk(c, under_sizeof)
                return

            # 필드 접근은 풀네임 1토큰으로 수집
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
        # 순서보존 dedupe
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
            # *(p+i) 같은 포인터 간접의 단순 패턴 (Unary * + Binary +|-)
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

    # 선언 초기화 번들 감지 헬퍼
    # 패턴으로 name[...] = { (배열 브레이스 초기화) 또는 name[...] = "..."(문자열 리터럴 초기화)를 체크
    # 그리고 직전 1~2개 평탄화 노드가 ArrayDeclaration/ArraySizeAllocation이며 이름이 같은지 확인 (번들 구조 보완)
    def _is_decl_init_trick(self, sid: int, name: str, assign_node: Dict[str, Any]) -> bool:
        code = assign_node.get("code") or ""
        if not name or not code:
            return False
        # Pattern: name[ ... ] = { ... }  or  name[ ... ] = "..."
        pat_brace = r"^\s*" + re.escape(name) + r"\s*\[[^\]]+\]\s*=\s*\{"
        pat_str = r"^\s*" + re.escape(name) + r"\s*\[[^\]]+\]\s*=\s*\""
        if re.search(pat_brace, code) or re.search(pat_str, code):
            return True

        # Inspect adjacent flattened nodes (ArrayDecl/ArraySizeAlloc + same name)
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
        """For AssignmentExpression only: (def_vars, uses[(var,role)], is_buffer_access, is_sink)"""
        def_vars: List[str] = []
        uses: List[Tuple[str, str]] = []
        iba, is_sink = 0, 0
        kids = assign_node.get("children", []) or []
        lhs = kids[0] if len(kids) >= 1 else None
        rhs = kids[1] if len(kids) >= 2 else None
        base_name: Optional[str] = None

        # --- helper: LHS 텍스트 기반 인덱싱 보조 감지
        # int buffer[10] = { 0 }; 와 같은 케이스를 지원하기 위함
        # buffer[ ... ] = 패턴이 있으면 is_buffer_access=1로 잡고, 인덱스가 비상수 식별자를 포함하면 is_sink=1
        def _lhs_textual_indexing(node: Dict[str, Any], name: str) -> Tuple[bool, bool]:
            """
            Detect name[ ... ] pattern on the left of '=' in the code string.
            return: (has_indexing, index_has_identifier_for_sink)
            - has_indexing: True if LHS has a subscript
            - index_has_identifier_for_sink: True if identifiers remain after removing sizeof(...)
            """
            code = (node.get("code") or "") if isinstance(node, dict) else ""
            if not code or not name:
                return (False, False)
            left = code.split("=", 1)[0]
            pattern = r"\b" + re.escape(name) + r"\s*\[([^\]]+)\]"
            m = re.search(pattern, left)
            if not m:
                return (False, False)
            idx_expr = m.group(1)
            # Check for identifiers after removing sizeof(...) fragments -> used only for sink determination
            idx_no_sizeof = re.sub(r"\bsizeof\s*\([^)]*\)", "", idx_expr)
            has_ident = bool(re.search(r"[A-Za-z_]\w*", idx_no_sizeof))
            return (True, has_ident)

        if isinstance(lhs, dict) and lhs.get("nodeType") == "ArraySubscriptExpression":
            # print( ... )
            base, index = (lhs.get("children") or [None, None])[:2]

            # LHS base = USE(주소 계산), DEF 아님
            if isinstance(base, dict):
                base_full = self._fullname_from_expr(base)  # deref/paren/cast/field까지 내부에서 처리
                if base_full and base_full not in KEYWORDS:
                    uses.append((base_full, "base"))
            # index USE
            has_runtime_index = False
            if isinstance(index, dict):
                # 1) 디버그/에지 생성을 위해 sizeof(...) 내부도 USE로 수집
                for t in self._idents_from_ast_node(index, skip_sizeof=False, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "index"))

                # 2) 싱크 판정은 '런타임 식별자' 존재 여부로 (sizeof 내부 식별자는 제외)
                for t in self._idents_from_ast_node(index, skip_sizeof=True, skip_callee=True):
                    if t and t not in KEYWORDS:
                        has_runtime_index = True
                        break

            iba = 1
            is_sink = 1 if has_runtime_index else 0  # 인덱스가 런타임 식별자를 포함할 때만

        elif isinstance(lhs, dict) and lhs.get("nodeType") == "Identifier":
            base_name = lhs.get("name")
            if isinstance(base_name, str) and base_name and base_name not in KEYWORDS:
                def_vars.append(base_name)
                _has_idx, _idx_has_ident = _lhs_textual_indexing(assign_node, base_name)
                if _has_idx:
                    # 선언 초기화 번들이면 런타임 접근으로 보지 않음
                    if not self._is_decl_init_trick(cur_sid, base_name, assign_node):
                        iba = 1
                        if _idx_has_ident:
                            is_sink = 1

        else:
            # 기타 LHS 표현식: 첫 식별자 DEF로 보수적 처리
            ids = self._idents_from_ast_node(lhs, skip_sizeof=True, skip_callee=True)
            if ids:
                def_vars.append(ids[0])

        # RHS 분석: 먼저 인덱스(role=index)와 베이스(role=base), 그 다음 value(중복/인덱스 제외)
        rhs_index_vars: Set[str] = set()
        if isinstance(rhs, dict) and rhs.get("nodeType") == "ArraySubscriptExpression":
            rk = rhs.get("children") or []
            rhs_base = rk[0] if len(rk) > 0 else None
            rhs_index = rk[1] if len(rk) > 1 else None
            # base USE (읽기)
            if isinstance(rhs_base, dict):
                rhs_base_full = self._fullname_from_expr(rhs_base)
                if rhs_base_full and rhs_base_full not in KEYWORDS:
                    uses.append((rhs_base_full, "base"))
            # index USE
            if isinstance(rhs_index, dict):
                for t in self._idents_from_ast_node(rhs_index, skip_sizeof=False, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "index"))
                        rhs_index_vars.add(t)

        return def_vars, uses, iba, is_sink

    def _array_decl_by_ast(self, decl: Dict[str, Any]) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        ArrayDeclaration / ArraySizeAllocation 처리:
        - def_vars: 배열 식별자
        - uses: 길이식에서 식별자 (단, sizeof(...) 내부는 USE로 세지지 않음)
        """
        def_vars: List[str] = []
        uses: List[Tuple[str, str]] = []

        nt = decl.get("nodeType")
        if nt == "ArrayDeclaration":
            nm = decl.get("name")
            if isinstance(nm, str) and nm and nm not in KEYWORDS:
                def_vars.append(nm)
            # 길이식 추출 (스키마에 따라 children[0] 등)
            kids = decl.get("children") or []
            length = kids[0] if kids else None
            if isinstance(length, dict):
                # ✅ sizeof 내부는 USE로 세지지 않음
                for t in self._idents_from_ast_node(length, skip_sizeof=True, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "size"))
        elif nt == "ArraySizeAllocation":
            # 필요 시 동일 규칙 적용
            kids = decl.get("children") or []
            length = kids[0] if kids else None
            if isinstance(length, dict):
                for t in self._idents_from_ast_node(length, skip_sizeof=True, skip_callee=True):
                    if t and t not in KEYWORDS:
                        uses.append((t, "size"))

        return def_vars, uses

    # ------------------------------
    # Calls: 역할 매핑 (AST 노드 인자)
    # ------------------------------
    def _call_arg_uses_ast(self, fname: str, arg_nodes: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
        """
        호출 인자에서 USE 변수 추출.
        - call_node 내부의 인자들을 역할별로 USE로 수집한다.
        - 역할: value/ index / size / base
        - ArraySubscriptExpression의 첨자(index) 식별자는 role="index" (※ sizeof(...) 내부 식별자는 제외)
        - API별 size 슬롯의 식별자는 role="size" (※ sizeof(...) 내부 식별자는 제외)


        - dst(목적지) 인자는 role="base" (필드 감도: base.field)
        - 그 밖의 식별자는 role="value"
        - size/index: DFG 에지는 런타임 의존만 생성해야 하므로 sizeof(...) 내부 식별자는 스킵한다.
        """
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

        # dst / size 인자 위치 매핑
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
            # 예) memset(&service, 0, sizeof(service))
            dst_pos, size_pos = 0, 2
        elif low in {"connect"}:
            # connect(int sockfd, const struct sockaddr *addr, socklen_t addrlen)
            # 예) connect(connectSocket, (struct sockaddr*)&service, sizeof(service)/
            # addr는 입력 포인터(쓰기 대상 아님) → dst_pos=None
            # addrlen은 size 성격 → size_pos=2
            dst_pos, size_pos = None, 2

        # 1) 모든 인자에서 배열 첨자(index) 먼저 수집 (sizeof 내부 식별자는 제외)
        for a in arg_nodes or []:
            if isinstance(a, dict) and a.get("nodeType") == "ArraySubscriptExpression":
                kids = a.get("children") or []
                idx_node = kids[1] if len(kids) > 1 else None
                if isinstance(idx_node, dict):
                    for t in self._idents_from_ast_node(idx_node, skip_sizeof=True, skip_callee=True):
                        _emit(t, "index")
                        index_vars.add(t)

        # 2) size 슬롯 처리: sizeof(...) 내부 식별자는 제외 (런타임 의존만 수집)
        if size_pos is not None and 0 <= size_pos < len(arg_nodes or []):
            size_arg = arg_nodes[size_pos]
            if isinstance(size_arg, dict):
                for t in self._idents_from_ast_node(size_arg, skip_sizeof=True, skip_callee=True):
                    _emit(t, "size")
                    size_vars.add(t)

        # 3) dst 슬롯 처리: 목적지(base) 표기 (필드 감도)
        if dst_pos is not None and 0 <= dst_pos < len(arg_nodes or []):
            dst_arg = arg_nodes[dst_pos]
            if isinstance(dst_arg, dict):
                for t in self._idents_from_ast_node(dst_arg, skip_sizeof=True, skip_callee=True):
                    logger.debug("%s: destination arg at position %s -> %s", fname, dst_pos, t)
                    _emit(t, "base")

                    base_vars.add(t)

        # 4) 나머지 인자들: value 표기
        for i, a in enumerate(arg_nodes or []):
            if not isinstance(a, dict):
                continue
            # ✅ dst/size 슬롯은 value 스캔에서 완전히 건너뜀 (중복 방지의 핵심)
            if i == dst_pos or i == size_pos:
                continue
            for t in self._idents_from_ast_node(a, skip_sizeof=True, skip_callee=True):
                # index/size/base로 이미 집계된 식별자는 value로 중복 집계하지 않음
                if t in index_vars or t in size_vars or t in base_vars:
                    continue
                _emit(t, "value")
            # print( ... )
        return out

    def _call_write_effects_ast(self, fname: str, arg_nodes: List[Dict[str, Any]]) -> List[str]:
        """
        호출의 '쓰기 효과(DEF)' 대상 식별자를 추출.
        - dst 인자(라이브러리별 위치)에 대해:
        * AddressOf/Paren/Cast 등을 언랩한 실제 대상 기준으로 DEF  # ★
        * MemberAccess -> 'base.field' 풀네임으로 DEF
        * Identifier   -> 이름으로 DEF
        - scanf/fscanf: 포맷 이후 인자들에서 '&x' 패턴은 x를 DEF
        (필드 주소 &s.field 도 지원)
        - 중복 제거 및 KEYWORDS 제외
        """
        defs: List[str] = []

        def _emit(name: str | None) -> None:
            if name and name not in KEYWORDS and name not in defs:
                defs.append(name)

        def _first_ident(node: Dict[str, Any] | None) -> str:
            ids = self._idents_from_ast_node(node, skip_sizeof=True, skip_callee=True)
            return ids[0] if ids else ""

        def _dst_fullname(node: Dict[str, Any] | None) -> str:
            """dst가 AddressOf/Paren/Cast 등을 포함해도 실제 대상 기준으로 풀네임/식별자 반환."""
            if not isinstance(node, dict):
                return ""
            # ★ 주소(&), 캐스트, 괄호 언랩
            core = unwrap_ast(node, strip_addr=True, strip_cast=True, strip_paren=True) or node  # ★
            full = self._fullname_from_expr(core)  # 'base.field' or ident
            if full:
                return full
            return _first_ident(core)

        def _get_arg(idx: int) -> Dict[str, Any] | None:
            nodes = arg_nodes or []
            return nodes[idx] if 0 <= idx < len(nodes) else None

        low = (fname or "").lower()

        # 1) 버퍼/문자열을 '목적지'로 쓰는 호출들: dst 슬롯 DEF
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
            # recv(int, void* buf, size_t, ...) / read(int, void* buf, size_t)
            # getline(char** lineptr, size_t* n, FILE*): 프로젝트 규칙 상 2번째 인자 DEF
            dst_idx = 1
            dst = _get_arg(dst_idx)
            _emit(_dst_fullname(dst))

        # 2) scanf/fscanf: 포맷 이후 인자들에서 '&x' 주소 전달 → x DEF
        if low in {"scanf", "fscanf"}:
            for a in (arg_nodes or [])[1:]:
                nm = self._extract_address_of_ident(a)
                if nm:
                    _emit(nm)
                    continue
                if isinstance(a, dict) and a.get("nodeType") in {"UnaryOperator", "UnaryExpression"}:
                    kids = a.get("children") or []
                    if kids:
                        full = self._fullname_from_expr(kids[0])  # & (MemberAccess)
                        _emit(full)

        return defs

    def _extract_address_of_ident(self, node: Dict[str, Any] | None) -> str:
        """scanf류 인자의 &v 에서 v 추출 (단순 패턴)"""
        if not isinstance(node, dict):
            return ""
        nt = node.get("nodeType")
        if nt in {"UnaryOperator", "UnaryExpression"} and node.get("operator") == "&":
            for ch in node.get("children", []) or []:
                if isinstance(ch, dict) and ch.get("nodeType") == "Identifier":
                    nm = ch.get("name")
                    if isinstance(nm, str):
                        return nm
        # 더 깊은 경우에도 첫 식별자 반환
        ids = self._idents_from_ast_node(node, skip_sizeof=True, skip_callee=True)
        return ids[0] if ids else ""

    # ------------------------------
    # Guard map (AST 조건 서브트리로 분석)
    # ------------------------------

    def _lower_from_for_init(self, for_node: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Detect lower-bound (x >= 0) evidence from ForStatement initializer like x = 0."""
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
                    # assume non-negative literal as lower guard
                    if int(val) >= 0:
                        res[nm] = {"lower": 1, "upper": 0, "upper_const": 0.0}
        return res

    def _build_guard_map(self) -> Dict[int, Dict[str, Dict[str, Any]]]:
        """Guard evidence per statement, propagated from each guarded block's head.

        Reads the AST pass's guard edges and spreads the enclosing condition's
        bound evidence over every statement the guard covers, following both
        statement order (SB) and parent/child (PC) edges.

        Policy, unchanged: an ``if`` applies its variable guards to the *then*
        branch only -- the else branch does not get the inverse. A loop applies
        its condition guards. A switch contributes only its kind.

        Returns ``{sid: {var: {kind, lower, upper, upper_const}, "*": ..., "__agg__": ...}}``
        where ``*`` and ``__agg__`` are the same aggregate object, used as the
        fallback when a variable has no entry of its own.
        """
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
        """Make sure ``self.idmap`` maps AST node id -> node, building it if absent."""
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
        """The original AST node for a statement sid, over three fallback routes."""
        # (a) the flat sid -> row index
        if isinstance(self.sid2flat, dict):
            oid = (self.sid2flat.get(sid) or {}).get("orig_id")
            if isinstance(oid, int):
                return self.idmap.get(oid)
        # (b) a linear scan of the AST pass's node list
        # (c) or of our own, if it carries orig_id directly
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
        """Bound evidence read off each control statement's own condition.

        Note the set of control statements here excludes ``SwitchStatement``: a
        switch contributes a guard *kind* but no per-variable bounds, so there is
        nothing to read from it. The module-level ``CONTROL_NODES`` does include
        it, which is why this keeps its own set.
        """
        ast_nodes = ast_res.get("nodes") or []
        out: Dict[int, Dict[str, Dict[str, Any]]] = {}

        for row in self.nodes or []:
            sid = row.get("sid")
            node_type = row.get("node_type_id") or row.get("node_type")
            # sid is always an int here (__init__ builds these rows), and a
            # non-int key could never be looked up by _propagate_guard anyway.
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

            # A for header can supply a lower bound the condition does not; its
            # upper bound, if any, does not override the condition's.
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
        """Spread one guard edge's evidence over every statement in its block."""
        if kind == GUARD_KIND_IF:
            # then-branch only; the else branch gets no inverted guard
            var_guards = (condition_guards.get(src_sid, {}) or {}) if branch == 0 else {}
        elif kind == GUARD_KIND_LOOP:
            var_guards = condition_guards.get(src_sid, {}) or {}
        else:  # switch: kind only
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
            entry["__agg__"] = entry["*"]  # deliberately the same object

            for successor in stmt_order.get(sid, []):
                if successor not in seen:
                    queue.append(successor)
            for successor in parent_child.get(sid, []):
                if successor not in seen:
                    queue.append(successor)

    def _guard_ctx_by_sid(self, sid: int) -> Dict[str, Any]:
        f = self._sid2feat.get(int(sid), {}) or {}
        # kind: 루프 안이면 2(while/for), 아니면 if(1) 또는 없음(0)
        kind = 2 if f.get("in_loop", 0) else (1 if f.get("ctx_guard_strength", 0) else 0)
        s = int(f.get("ctx_guard_strength", 0) or 0)  # 0:none, 1:lower, 2:upper, 3:both
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
