"""
Declaration Processor for DFG Extraction

This module handles variable declarations, array declarations,
and related DEF/USE relationships.
"""

from typing import Any, Dict, List, Optional

from dfg.constants import FLOW_ID, KEYWORDS


class DeclarationProcessor:
    """Processes declaration statements and related DEF/USE relationships."""

    def __init__(self, dfg_extractor, state):
        self.dfg = dfg_extractor
        self.state = state
        self.edge_manager: Optional[Any] = None  # Will be set by StatementProcessor

    def process_declaration(self, sid: int, orig: Dict[str, Any]) -> None:
        """Process declaration nodes."""
        nm = orig.get("name")
        if isinstance(nm, str) and nm and nm not in KEYWORDS:
            self.state.last_def[nm] = sid
            self.state.def_vars_by_sid[sid].add(nm)

    def process_array_declaration(self, sid: int, orig: Dict[str, Any]) -> None:
        """Process array declaration nodes."""
        def_vars, uses = self.dfg._array_decl_by_ast(orig)

        for v, role in uses:
            self._add_use_edge(v, role, sid)

        for dv in def_vars:
            if dv and dv not in KEYWORDS:
                self.state.last_def[dv] = sid
                self.state.def_vars_by_sid[sid].add(dv)

    def is_declaration(self, node_type: str) -> bool:
        """Check if this is a declaration node."""
        return node_type in {
            "VariableDeclaration",
            "ParameterDeclaration",
            "PointerDeclaration",
        }

    def is_array_decl(self, node_type: str) -> bool:
        """Check if this is an array declaration node."""
        return node_type in {"ArrayDeclaration", "ArraySizeAllocation"}

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
