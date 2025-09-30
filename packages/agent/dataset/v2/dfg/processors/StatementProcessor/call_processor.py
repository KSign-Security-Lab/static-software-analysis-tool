"""
Call Processor for DFG Extraction

This module handles function call processing, including argument analysis,
sink detection, and call-specific DEF/USE relationships.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple

from dfg.constants import FLOW_ID, KEYWORDS


class CallProcessor:
    """Processes function calls and sink analysis."""

    def __init__(self, dfg_extractor, state):
        self.dfg = dfg_extractor
        self.state = state
        self.edge_manager: Optional[Any] = None  # Will be set by StatementProcessor

        # Function classification sets
        self.UNBOUNDED_SINKS = {"gets", "strcpy", "strcat", "sprintf", "vsprintf"}
        self.BOUNDED_SINKS = {
            "memcpy",
            "memmove",
            "strncpy",
            "snprintf",
            "vsnprintf",
            "fgets",
            "read",
            "recv",
            "getline",
        }

    def process_statement_level_call(self, sid: int, orig: Dict[str, Any]) -> None:
        """Process statement-level call nodes (special case)."""
        print(
            f"(특수) 문장-수준 호출 노드가 ArgList만 가리키는 경우: 여기서 호출 자체 처리 : node = {orig.get('code', '')}"
        )

        fname = self.dfg._callee_name_from_arglist(self.dfg.ast_json, orig)
        base = (fname or "").lower()
        arg_nodes = orig.get("children") or []

        # Process argument uses
        for v, role in self.dfg._call_arg_uses_ast(base, arg_nodes):
            if role == "base":
                self._add_use_edge(v, "base", sid)
                continue
            self.state.used_by_call_stmt.add(v)
            self._add_use_edge(v, role, sid)

        # Process write effects
        for v in self.dfg._call_write_effects_ast(base, arg_nodes):
            if v and v not in KEYWORDS:
                self.state.last_def[v] = sid
                self.state.def_vars_by_sid[sid].add(v)
                self.state.exclude_vars_stmt.add(v)

        # Process sink flags
        self._process_call_sink_flags(sid, base, arg_nodes)

    def process_generic_calls(self, sid: int, orig: Dict[str, Any]) -> None:
        """Process generic calls within statements."""
        for fname, arg_nodes in self.dfg._iter_calls_ast(orig):
            base = (fname or "").lower()

            # Process argument uses
            for v, role in self.dfg._call_arg_uses_ast(fname or "", arg_nodes):
                if role == "base":
                    self._add_use_edge(v, "base", sid)
                    continue
                self.state.used_by_call_stmt.add(v)
                self._add_use_edge(v, role, sid)

            # Process write effects
            for v in self.dfg._call_write_effects_ast(fname or "", arg_nodes):
                if v and v not in KEYWORDS:
                    self.state.last_def[v] = sid
                    self.state.def_vars_by_sid[sid].add(v)
                    self.state.exclude_vars_stmt.add(v)

            # Process sink flags
            self._process_call_sink_flags(sid, base, arg_nodes)

    def _process_call_sink_flags(
        self, sid: int, base: str, arg_nodes: List[Dict[str, Any]]
    ) -> None:
        """Process sink flags for function calls."""
        dst_arg, size_arg = self.dfg._pick_dst_size_args(base, arg_nodes)

        # Check dst indexing
        dst_indexed = 1 if self.dfg._has_indexing(dst_arg, skip_sizeof=True) else 0

        # Check len-linked and size nonconst
        size_txt = (size_arg.get("code") or "") if isinstance(size_arg, dict) else ""
        dst_names = (
            set(self.dfg._idents_from_ast_node(dst_arg))
            if isinstance(dst_arg, dict)
            else set()
        )
        dst_full = (
            self.dfg._fullname_from_expr(dst_arg) if isinstance(dst_arg, dict) else None
        )
        if dst_full:
            dst_names.add(dst_full)

        linked = 0
        if size_txt and dst_names:
            sizeof_hits = any(
                ("sizeof(" + dn + ")") in size_txt
                or ("sizeof(*" + dn + ")") in size_txt
                or ("sizeof(" + dn + "[0])") in size_txt
                for dn in dst_names
            )
            linked = 1 if sizeof_hits else 0

        # Check size nonconst
        size_txt_wo_sizeof = re.sub(r"\bsizeof\s*\([^)]*\)", "", size_txt)
        nonconst = (
            1 if (size_txt and re.search(r"[A-Za-z_]\w*", size_txt_wo_sizeof)) else 0
        )

        if size_txt and ("sizeof(" in size_txt):
            if not any(("sizeof(" + dn + ")") in size_txt for dn in dst_names):
                nonconst = 1
            if dst_full and "." in dst_full:
                base_only = dst_full.split(".")[0]
                if ("sizeof(" + base_only + ")") in size_txt:
                    nonconst = 1

        # Apply sink flags
        if base in self.UNBOUNDED_SINKS:
            self.state.node_feat[sid].update(
                {
                    "is_sink_call_unbounded": 1,
                    "call_danger_unbounded": 1,
                    "call_dst_indexed": max(
                        self.state.node_feat[sid]["call_dst_indexed"], dst_indexed
                    ),
                }
            )
        elif base in self.BOUNDED_SINKS:
            self.state.node_feat[sid].update(
                {
                    "is_sink_call_bounded": 1,
                    "call_dst_indexed": max(
                        self.state.node_feat[sid]["call_dst_indexed"], dst_indexed
                    ),
                    "call_len_linked_to_dst": max(
                        self.state.node_feat[sid]["call_len_linked_to_dst"], linked
                    ),
                    "call_size_nonconst": max(
                        self.state.node_feat[sid]["call_size_nonconst"], nonconst
                    ),
                }
            )

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
