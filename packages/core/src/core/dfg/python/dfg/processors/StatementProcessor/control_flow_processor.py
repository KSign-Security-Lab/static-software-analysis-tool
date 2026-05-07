"""
Control Flow Processor for DFG Extraction

This module handles control flow statements (if, for, while, etc.),
including condition analysis and loop variable handling.
"""

from typing import Any, Dict, List, Optional, Set

from dfg.constants import KEYWORDS


class ControlFlowProcessor:
    """Processes control flow statements and related DEF/USE relationships."""

    def __init__(self, dfg_extractor, state):
        self.dfg = dfg_extractor
        self.state = state
        self.edge_manager: Optional[Any] = None  # Will be set by StatementProcessor

        self.CONTROL_NODES = {
            "IfStatement",
            "ForStatement",
            "WhileStatement",
            "DoWhileStatement",
            "DoStatement",
        }

    def process_control_node(
        self, sid: int, node_type: str, orig: Dict[str, Any]
    ) -> None:
        """Process control flow nodes (if, for, while, etc.)."""
        cond_node = self.dfg._get_condition_node(node_type, orig)
        if cond_node is None:
            return

        # Handle ForStatement header DEFs
        def_names = set()
        if node_type == "ForStatement":
            def_names = self._extract_for_header_defs(orig)

            # Apply DEFs before processing condition
            for v in sorted(def_names):
                self.state.last_def[v] = sid
                self.state.def_vars_by_sid[sid].add(v)

        # Reset control node features
        nf = self.state.node_feat[sid]
        nf.update(
            {
                "is_buffer_access": 0,
                "is_sink_assign": 0,
                "is_sink_call_unbounded": 0,
                "is_sink_call_bounded": 0,
                "call_dst_indexed": 0,
                "call_len_linked_to_dst": 0,
                "call_size_nonconst": 0,
                "call_danger_unbounded": 0,
            }
        )

        nf["def_count"] = len(self.state.def_vars_by_sid[sid])
        nf["use_count"] = len(self.state.use_vars_by_sid[sid])

    def _extract_for_header_defs(self, orig: Dict[str, Any]) -> Set[str]:
        """Extract DEF variables from ForStatement header."""
        def_names = set()
        kids = orig.get("children") or []
        init = kids[0] if len(kids) >= 1 else None
        inc = kids[2] if len(kids) >= 3 else None

        # Process initialization: i = <expr>
        if isinstance(init, dict) and init.get("nodeType") == "AssignmentExpression":
            lhs, rhs = (init.get("children") or [None, None])[:2]
            if isinstance(lhs, dict) and lhs.get("nodeType") == "Identifier":
                nm = lhs.get("name")
                if isinstance(nm, str) and nm and nm not in KEYWORDS:
                    def_names.add(nm)

        # Process increment: ++i, i++, i += k, etc.
        if isinstance(inc, dict):
            for t in self.dfg._idents_from_ast_node(
                inc, skip_sizeof=True, skip_callee=True
            ):
                if t and t not in KEYWORDS:
                    def_names.add(t)

        return def_names

    def is_control_node(self, node_type: str) -> bool:
        """Check if this is a control flow node."""
        return node_type in self.CONTROL_NODES
