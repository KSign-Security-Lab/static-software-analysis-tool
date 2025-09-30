"""
Assignment Processor for DFG Extraction

This module handles assignment expressions, including LHS/RHS analysis,
pointer vs object distinction, and assignment-specific DEF/USE relationships.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from dfg.constants import FLOW_ID, KEYWORDS


class AssignmentProcessor:
    """Processes assignment expressions and related DEF/USE relationships."""

    def __init__(self, dfg_extractor, state):
        self.dfg = dfg_extractor
        self.state = state
        self.edge_manager: Optional[Any] = None  # Will be set by StatementProcessor

    def process_assignment(
        self, sid: int, orig: Dict[str, Any], assign_rhs_has_call: bool
    ) -> None:
        """Process assignment expressions."""
        # Handle LHS array indexing
        self._process_lhs_array_indexing(sid, orig)

        # Extract DEF/USE from assignment
        def_vars, uses, iba, sink = self.dfg._assignment_by_ast(orig, sid)

        # Process LHS base handling
        self._process_lhs_base_handling(sid, orig, def_vars, uses)

        # Filter uses to avoid duplicates
        uses = self._filter_assignment_uses(uses, orig, assign_rhs_has_call)

        # Apply DEFs and USEs
        for v, role in uses:
            self._add_use_edge(v, role, sid)

        for dv in def_vars:
            if dv and dv not in KEYWORDS:
                self.state.last_def[dv] = sid
                self.state.def_vars_by_sid[sid].add(dv)

        # Handle RHS call split
        self._process_rhs_call_split(sid, orig)

        # Update flags
        if iba:
            self.state.iba_by_sid[sid] = 1
        if sink:
            self.state.sink_assign_by_sid[sid] = 1

    def _process_lhs_array_indexing(self, sid: int, orig: Dict[str, Any]) -> None:
        """Process LHS array indexing for index role."""
        chs = orig.get("children") or []
        lhs = chs[0] if len(chs) >= 1 else None

        if isinstance(lhs, dict) and lhs.get("nodeType") == "ArraySubscriptExpression":
            kids = lhs.get("children") or []
            idx = kids[1] if len(kids) > 1 else None
            if isinstance(idx, dict):
                for v in self.dfg._idents_from_ast_node(
                    idx, skip_sizeof=True, skip_callee=True
                ):
                    if v:
                        self._add_use_edge(v, "index", sid)

    def _process_lhs_base_handling(
        self,
        sid: int,
        orig: Dict[str, Any],
        def_vars: List[str],
        uses: List[Tuple[str, str]],
    ) -> None:
        """Process LHS base handling for pointer vs object distinction."""
        chs = orig.get("children") or []
        lhs = chs[0] if len(chs) >= 1 else None
        lhs_base_name = None
        lhs_nt = None
        lhs_is_pointer_base = False
        lhs_is_object_base = False

        if isinstance(lhs, dict):
            lhs_nt = lhs.get("nodeType")

            if lhs_nt == "ArraySubscriptExpression":
                kids = lhs.get("children") or []
                base = kids[0] if len(kids) > 0 else None
                if isinstance(base, dict):
                    lhs_base_name = self.dfg._fullname_from_expr(base)
                    if not lhs_base_name and base.get("nodeType") == "Identifier":
                        lhs_base_name = base.get("name")

                    # Check for pointer base
                    if base.get("nodeType") == "PointerDereference":
                        lhs_is_pointer_base = True

                    # Check for object base
                    if not lhs_is_pointer_base and base.get("nodeType") in {
                        "Identifier",
                        "MemberAccess",
                    }:
                        lhs_is_object_base = True

            elif lhs_nt == "PointerDereference":
                inner = (lhs.get("children") or [None])[0]
                if isinstance(inner, dict):
                    lhs_base_name = self.dfg._fullname_from_expr(inner)
                    if not lhs_base_name and inner.get("nodeType") == "Identifier":
                        lhs_base_name = inner.get("name")

                # Check if it's a real dereference
                lhs_code = (lhs.get("code") or "").strip()
                if lhs_code.startswith("*"):
                    lhs_is_pointer_base = True
                else:
                    lhs_is_object_base = True

            elif lhs_nt in {"Identifier", "MemberAccess"}:
                lhs_base_name = self.dfg._fullname_from_expr(lhs) or lhs.get("name")
                lhs_is_object_base = True

        # Apply base handling logic
        if lhs_base_name and lhs_base_name not in KEYWORDS:
            if lhs_is_object_base:
                # Object base: add DEF, handle container access
                if lhs_base_name not in def_vars:
                    def_vars.append(lhs_base_name)

                if lhs_nt in {
                    "ArraySubscriptExpression",
                    "MemberAccess",
                } and isinstance(lhs, dict):
                    self._process_container_access(sid, lhs, lhs_base_name)

                # Remove base from uses to avoid duplication
                uses = [
                    (v, r)
                    for (v, r) in uses
                    if not (v == lhs_base_name and r == "base")
                ]

            elif lhs_is_pointer_base:
                # Pointer base: no DEF, ensure base USE exists
                def_vars = [dv for dv in def_vars if dv != lhs_base_name]
                if (lhs_base_name, "base") not in uses:
                    uses.append((lhs_base_name, "base"))

    def _process_container_access(
        self, sid: int, lhs: Dict[str, Any], lhs_base_name: str
    ) -> None:
        """Process container access (array/field) with guard injection."""
        # Extract index variables
        idx_vars = []
        if lhs.get("nodeType") == "ArraySubscriptExpression":
            kids = lhs.get("children") or []
            idx = kids[1] if len(kids) > 1 else None
            if isinstance(idx, dict):
                idx_vars = self.dfg._idents_from_ast_node(
                    idx, skip_sizeof=True, skip_callee=True
                )

        # Aggregate guards from index variables
        gm_here = self.dfg.guard_map.get(sid, {})
        agg = {"kind": 0, "lower": 0, "upper": 0, "upper_const": 0.0}

        for iv in idx_vars or []:
            g = gm_here.get(iv) or gm_here.get("*") or gm_here.get("__agg__") or {}
            agg["lower"] |= int(g.get("lower", 0))
            agg["upper"] |= int(g.get("upper", 0))
            agg["upper_const"] = max(
                agg["upper_const"], float(g.get("upper_const", 0.0))
            )
            if not agg["kind"]:
                agg["kind"] = int(g.get("kind", 0))

        if not agg["kind"]:
            gf = gm_here.get("*") or gm_here.get("__agg__") or {}
            agg["kind"] = int(gf.get("kind", 0))
            agg["lower"] |= int(gf.get("lower", 0))
            agg["upper"] |= int(gf.get("upper", 0))
            agg["upper_const"] = max(
                agg["upper_const"], float(gf.get("upper_const", 0.0))
            )

        # Inject aggregated guards
        gm_dst = self.dfg.guard_map.setdefault(sid, {})
        gm_dst["*"] = agg.copy()
        gm_dst["__agg__"] = gm_dst["*"]

        # Add base USE edge
        self._add_use_edge(lhs_base_name, "base", sid)

    def _filter_assignment_uses(
        self,
        uses: List[Tuple[str, str]],
        orig: Dict[str, Any],
        assign_rhs_has_call: bool,
    ) -> List[Tuple[str, str]]:
        """Filter assignment uses to avoid duplicates."""
        # Remove RHS value uses if there's a call (call node owns them)
        if assign_rhs_has_call:
            try:
                chs_rhs = orig.get("children") or []
                rhs = chs_rhs[1] if len(chs_rhs) >= 2 else None
                rhs_call = (
                    self.dfg._find_first_call_node(rhs)
                    if isinstance(rhs, dict)
                    else None
                )
                if isinstance(rhs_call, dict):
                    uses = [(v, r) for (v, r) in uses if r != "value"]
            except Exception:
                pass

        # Remove excluded and call-used variables
        uses = [
            (v, r)
            for (v, r) in uses
            if v not in self.state.exclude_vars_stmt
            and v not in self.state.used_by_call_stmt
        ]

        return uses

    def _process_rhs_call_split(self, sid: int, orig: Dict[str, Any]) -> None:
        """Process RHS call split handling."""
        try:
            chs2 = orig.get("children") or []
            rhs2 = chs2[1] if len(chs2) >= 2 else None
            calln = (
                self.dfg._find_first_call_node(rhs2) if isinstance(rhs2, dict) else None
            )
            if isinstance(calln, dict):
                cid = calln.get("id")
                sid_call = self.dfg.orig2sid.get(cid) if cid is not None else None
                if isinstance(sid_call, int) and self.dfg._sb_has(sid_call, sid):
                    gi = (self.dfg.guard_map.get(sid) or {}).get("__agg__") or {}
                    self.dfg.edges_defuse.append(
                        (
                            sid_call,
                            sid,
                            {
                                "var_key": f"$ret@{sid_call}",
                                "feat": {
                                    "flow_id": FLOW_ID["value"],
                                    "guard_kind": int(gi.get("kind", 0)),
                                    "has_lower_guard": int(gi.get("lower", 0)),
                                    "has_upper_guard": int(gi.get("upper", 0)),
                                    "upper_guard_norm": float(
                                        gi.get("upper_const", 0.0)
                                    ),
                                },
                                "debug": {"var_key": f"$ret@{sid_call}"},
                            },
                        )
                    )
        except Exception:
            pass

    def _add_use_edge(self, var: str, role: str, dst_sid: int) -> None:
        """Add a USE edge with proper guard handling."""
        if not var or var in KEYWORDS:
            return

        # Track USE for counting (base excluded)
        if role != "base":
            self.state.use_vars_by_sid[dst_sid].add(var)

        # Create DEF→USE edge if last DEF exists
        if var not in self.state.last_def:
            return

        src = self.state.last_def[var]
        fid = FLOW_ID.get(role or "value", FLOW_ID["value"])

        key = (src, dst_sid, var, fid)
        if key in self.state.seen_edges:
            return
        self.state.seen_edges.add(key)

        # Get guard information for this statement
        dst_guards = self.dfg.guard_map.get(dst_sid, {})
        g_var = dst_guards.get(var) or {}
        g_all = dst_guards.get("*") or {}
        g_agg = dst_guards.get("__agg__") or {}

        # Determine guard kind and values
        kind = self.dfg._pick_kind(g_var, g_all, g_agg)
        has_lower = (
            self.dfg._as_int(g_var.get("lower", 0))
            | self.dfg._as_int(g_all.get("lower", 0))
            | self.dfg._as_int(g_agg.get("lower", 0))
        )
        has_upper = (
            self.dfg._as_int(g_var.get("upper", 0))
            | self.dfg._as_int(g_all.get("upper", 0))
            | self.dfg._as_int(g_agg.get("upper", 0))
        )
        upper_norm = max(
            self.dfg._as_float(g_var.get("upper_const", 0.0)),
            self.dfg._as_float(g_all.get("upper_const", 0.0)),
            self.dfg._as_float(g_agg.get("upper_const", 0.0)),
        )

        # Add edge to DFG
        self.dfg.edges_defuse.append(
            (
                src,
                dst_sid,
                {
                    "var_key": f"{var}@{src}",
                    "flow_id": fid,
                    "guard_kind": kind,
                    "has_lower_guard": has_lower,
                    "has_upper_guard": has_upper,
                    "upper_guard_norm": upper_norm,
                },
            )
        )
