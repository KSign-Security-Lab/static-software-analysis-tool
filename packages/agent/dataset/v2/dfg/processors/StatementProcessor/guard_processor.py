"""
Guard Processor for DFG Extraction

This module handles guard analysis, edge creation with guard information,
and centralized DEF/USE edge management.
"""

from typing import Any, Dict, List, Optional, Set, Tuple

from dfg.constants import FLOW_ID, KEYWORDS


class GuardProcessor:
    """Processes guard information and creates DEF/USE edges."""

    def __init__(self, dfg_extractor, state):
        self.dfg = dfg_extractor
        self.state = state
        self.edge_manager: Optional[Any] = None  # Will be set by StatementProcessor

    def add_use_edge(self, var: str, role: str, dst_sid: int) -> None:
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

    def process_generic_statement(self, sid: int, orig: Dict[str, Any]) -> None:
        """Process generic statements (value USE scanning)."""
        if not isinstance(orig, dict):
            return

        # Scan for identifiers
        for t in self.dfg._idents_from_ast_node(
            orig, skip_sizeof=True, skip_callee=True
        ):
            if t in self.state.exclude_vars_stmt or t in self.state.used_by_call_stmt:
                continue
            self.add_use_edge(t, "value", sid)

    def ensure_feat(self, sid: int, node_type_id: str) -> None:
        """Ensure feature and debug containers exist for a node."""
        if sid not in self.state.node_feat:
            self.state.node_feat[sid] = {
                "node_type_id": node_type_id,
                "in_degree_dfg": 0,
                "out_degree_dfg": 0,
                "def_count": 0,
                "use_count": 0,
                "is_buffer_access": 0,
                "is_sink_assign": 0,
                "is_sink_call_unbounded": 0,
                "is_sink_call_bounded": 0,
                "call_dst_indexed": 0,
                "call_len_linked_to_dst": 0,
                "call_size_nonconst": 0,
                "call_danger_unbounded": 0,
            }
        if sid not in self.state.node_debug:
            self.state.node_debug[sid] = {"code": "", "def_vars": [], "use_vars": []}
