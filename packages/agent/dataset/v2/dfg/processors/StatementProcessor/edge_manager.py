"""
Edge Manager for DFG Extraction

This module provides centralized edge creation and management
to ensure consistent edge construction across all processors.
"""

from dfg.constants import FLOW_ID, KEYWORDS


class EdgeManager:
    """Centralized edge creation and management."""

    def __init__(self, dfg_extractor, state):
        self.dfg = dfg_extractor
        self.state = state
        self.debugger = None  # Will be set by debug system if enabled

    def set_debugger(self, debugger):
        """Set the debugger for edge tracking."""
        self.debugger = debugger

    def add_use_edge(self, var: str, role: str, dst_sid: int) -> None:
        """Add a USE edge with proper guard handling."""
        if not var or var in KEYWORDS:
            if self.debugger:
                self.debugger.log_missed_edge(
                    0, dst_sid, var, role, "Invalid variable or keyword"
                )
            return

        # Track USE for counting (base excluded)
        if role != "base":
            self.state.use_vars_by_sid[dst_sid].add(var)

        # Log the use if debugger is enabled
        if self.debugger:
            dst_code = self._get_code_for_sid(dst_sid)
            dst_type = self._get_type_for_sid(dst_sid)
            self.debugger.log_use(var, role, dst_sid, dst_type, dst_code)

        # Create DEF→USE edge if last DEF exists
        if var not in self.state.last_def:
            if self.debugger:
                self.debugger.log_missed_edge(
                    0, dst_sid, var, role, "No previous definition found"
                )
            return

        src = self.state.last_def[var]
        fid = FLOW_ID.get(role or "value", FLOW_ID["value"])

        key = (src, dst_sid, var, fid)
        if key in self.state.seen_edges:
            if self.debugger:
                self.debugger.log_missed_edge(
                    src, dst_sid, var, role, "Duplicate edge already exists"
                )
            return
        self.state.seen_edges.add(key)

        if self.debugger:
            self.debugger.log_potential_edge(
                src, dst_sid, var, role, "DEF->USE relationship exists"
            )

        # Get guard information for this statement
        try:
            dst_guards = self.dfg.guard_map.get(dst_sid, {})
            g_var = dst_guards.get(var) or {}
            g_all = dst_guards.get("*") or {}
            g_agg = dst_guards.get("__agg__") or {}
        except Exception as e:
            if self.debugger:
                self.debugger.log_guard_issue(
                    dst_sid, var, f"Guard map access error: {e}"
                )
            return

        # Determine guard kind and values
        try:
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
        except Exception as e:
            if self.debugger:
                self.debugger.log_guard_issue(
                    dst_sid, var, f"Guard processing error: {e}"
                )
            return

        # Add edge to DFG
        try:
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
            if self.debugger:
                self.debugger.log_created_edge(src, dst_sid, var, role, fid)
        except Exception as e:
            if self.debugger:
                self.debugger.log_missed_edge(
                    src, dst_sid, var, role, f"Edge creation error: {e}"
                )

    def add_def(self, var: str, sid: int, node_type: str, code: str) -> None:
        """Add a variable definition."""
        if var and var not in KEYWORDS:
            self.state.last_def[var] = sid
            if self.debugger:
                self.debugger.log_def(var, sid, node_type, code)

    def _get_code_for_sid(self, sid: int) -> str:
        """Get code for a statement ID."""
        try:
            for node in self.dfg.nodes:
                if node.get("sid") == sid:
                    return node.get("code", "")
        except Exception:
            pass
        return ""

    def _get_type_for_sid(self, sid: int) -> str:
        """Get node type for a statement ID."""
        try:
            for node in self.dfg.nodes:
                if node.get("sid") == sid:
                    return node.get("node_type_id", "")
        except Exception:
            pass
        return ""
