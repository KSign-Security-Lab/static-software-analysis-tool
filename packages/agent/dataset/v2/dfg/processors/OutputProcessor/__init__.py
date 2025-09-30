"""
Output Processor for DFG Extraction

This module handles the generation of final DFG output including
node features, edge formatting, and degree calculations.
"""

from typing import Any, Dict, List

from dfg.processors.StatementProcessor import ProcessingState


class OutputProcessor:
    """Handles final DFG output generation."""

    def __init__(self, dfg_extractor):
        self.dfg = dfg_extractor

    def build_final_output(
        self, state: ProcessingState, deg_in: Dict[int, int], deg_out: Dict[int, int]
    ) -> Dict[str, Any]:
        """Build the final output with nodes and edges."""
        out_nodes: List[Dict[str, Any]] = []

        for meta in self.dfg.nodes:
            sid = meta["sid"]
            code = meta["code"]
            node_type = meta["node_type_id"]

            # Ensure feature containers exist
            self._ensure_feat(sid, node_type, state.node_feat, state.node_debug)

            # Adjust use list for Assignment with RHS call
            ulist = self._process_use_list(sid, node_type, state)

            # Process def list
            dlist = sorted(
                [
                    x
                    for x in state.def_vars_by_sid.get(sid, set())
                    if x and x != "<empty>"
                ]
            )

            # Update features
            feat = state.node_feat[sid]
            feat["in_degree_dfg"] = deg_in.get(sid, 0)
            feat["out_degree_dfg"] = deg_out.get(sid, 0)
            feat["def_count"] = len(dlist)
            feat["use_count"] = len(ulist)
            feat["is_buffer_access"] = 1 if state.iba_by_sid.get(sid, 0) else 0
            feat["is_sink_assign"] = 1 if state.sink_assign_by_sid.get(sid, 0) else 0

            # AssignmentExpression call neutrality
            if node_type == "AssignmentExpression":
                feat["is_sink_call_unbounded"] = 0
                feat["is_sink_call_bounded"] = 0
                feat["call_dst_indexed"] = 0
                feat["call_len_linked_to_dst"] = 0
                feat["call_size_nonconst"] = 0
                feat["call_danger_unbounded"] = 0

            # Update debug info
            dbg = state.node_debug[sid]
            dbg["code"] = code
            dbg["def_vars"] = dlist
            dbg["use_vars"] = ulist

            # Attach orig_id
            flat_row = self.dfg._find_ast_row_by_sid(sid)
            orig_id = flat_row.get("orig_id") if isinstance(flat_row, dict) else None

            out_nodes.append(
                {"sid": sid, "orig_id": orig_id, "feat": feat, "debug": dbg}
            )

        # Build edges
        out_edges = self._build_edges()

        return {"nodes": out_nodes, "edges_dfg": out_edges}

    def calculate_degrees(self) -> tuple[Dict[int, int], Dict[int, int]]:
        """Calculate in-degree and out-degree for all nodes."""
        deg_in = {n["sid"]: 0 for n in self.dfg.nodes}
        deg_out = {n["sid"]: 0 for n in self.dfg.nodes}

        for s, d, _ in self.dfg.edges_defuse:
            if s in deg_out:
                deg_out[s] += 1
            if d in deg_in:
                deg_in[d] += 1

        return deg_in, deg_out

    def _process_use_list(
        self, sid: int, node_type: str, state: ProcessingState
    ) -> List[str]:
        """Process use list for assignment with RHS call."""
        ulist = sorted(
            [x for x in state.use_vars_by_sid.get(sid, set()) if x and x != "<empty>"]
        )

        try:
            if node_type == "AssignmentExpression":
                row = self.dfg.sid2flat.get(sid, {}) or {}
                oid = row.get("orig_id")
                an = self.dfg.idmap.get(oid) if isinstance(oid, int) else None
                kids = an.get("children") or [] if isinstance(an, dict) else []
                rhs = kids[1] if len(kids) >= 2 else None
                if isinstance(rhs, dict) and isinstance(
                    self.dfg._find_first_call_node(rhs), dict
                ):
                    rhs_idents = set(
                        self.dfg._idents_from_ast_node(
                            rhs, skip_sizeof=True, skip_callee=True
                        )
                    )
                    ulist = [x for x in ulist if x not in rhs_idents]
        except Exception:
            pass

        return ulist

    def _build_edges(self) -> List[List[Any]]:
        """Build final edge output."""
        out_edges: List[List[Any]] = []
        for s, d, attr in self.dfg.edges_defuse:
            out_edges.append(
                [
                    s,
                    d,
                    {
                        "feat": {
                            "flow_id": attr.get("flow_id", 1),
                            "guard_kind": attr.get("guard_kind", 0),
                            "has_lower_guard": attr.get("has_lower_guard", 0),
                            "has_upper_guard": attr.get("has_upper_guard", 0),
                            "upper_guard_norm": attr.get("upper_guard_norm", 0.0),
                        },
                        "debug": {"var_key": attr.get("var_key", "")},
                    },
                ]
            )
        return out_edges

    def _ensure_feat(
        self,
        sid: int,
        node_type_id: str,
        node_feat: Dict[int, Dict[str, Any]],
        node_debug: Dict[int, Dict[str, Any]],
    ) -> None:
        """Ensure feature and debug containers exist for a node."""
        if sid not in node_feat:
            node_feat[sid] = {
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
        if sid not in node_debug:
            node_debug[sid] = {"code": "", "def_vars": [], "use_vars": []}
