"""
Statement Processor for DFG Extraction

This module coordinates the processing of different types of AST statements
by delegating to specialized processors.
"""

from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from .assignment_processor import AssignmentProcessor
from .call_processor import CallProcessor
from .control_flow_processor import ControlFlowProcessor
from .declaration_processor import DeclarationProcessor
from .edge_manager import EdgeManager
from .guard_processor import GuardProcessor


class ProcessingState:
    """Centralized state management for DFG processing."""

    def __init__(self):
        # Core tracking variables
        self.last_def: Dict[str, int] = {}
        self.seen_edges: Set[Tuple[int, int, str, int]] = set()

        # Variable tracking by statement ID
        self.use_vars_by_sid: Dict[int, Set[str]] = defaultdict(set)
        self.def_vars_by_sid: Dict[int, Set[str]] = defaultdict(set)
        self.iba_by_sid: Dict[int, int] = defaultdict(int)  # is_buffer_access
        self.sink_assign_by_sid: Dict[int, int] = defaultdict(int)  # is_sink_assign

        # Node features and debug info
        self.node_feat: Dict[int, Dict[str, Any]] = {}
        self.node_debug: Dict[int, Dict[str, Any]] = {}

        # Statement-level tracking
        self.exclude_vars_stmt: Set[str] = set()
        self.used_by_call_stmt: Set[str] = set()


class StatementProcessor:
    """Coordinates processing of different types of AST statements using specialized processors."""

    def __init__(self, dfg_extractor):
        self.dfg = dfg_extractor
        self.state = ProcessingState()

        # Initialize edge manager
        self.edge_manager = EdgeManager(self.dfg, self.state)

        # Initialize specialized processors
        self.guard_processor = GuardProcessor(dfg_extractor, self.state)
        self.call_processor = CallProcessor(dfg_extractor, self.state)
        self.assignment_processor = AssignmentProcessor(dfg_extractor, self.state)
        self.control_processor = ControlFlowProcessor(dfg_extractor, self.state)
        self.declaration_processor = DeclarationProcessor(dfg_extractor, self.state)

        # Pass edge manager to all processors
        self.guard_processor.edge_manager = self.edge_manager
        self.call_processor.edge_manager = self.edge_manager
        self.assignment_processor.edge_manager = self.edge_manager
        self.control_processor.edge_manager = self.edge_manager
        self.declaration_processor.edge_manager = self.edge_manager

    def process_all_statements(self, nodes: List[Dict[str, Any]]) -> None:
        """Process all AST nodes to extract DEF/USE relationships."""
        # Initialize parameter DEFs
        self._process_parameters()

        # Process each statement
        for row in nodes:
            self._process_single_statement(row)

    def _process_parameters(self) -> None:
        """Process function parameters as initial DEFs."""
        for p in self.dfg.param_names:
            if p and p != "<empty>":
                self.state.last_def[p] = 0
                self.state.def_vars_by_sid[0].add(p)

    def _process_single_statement(self, row: Dict[str, Any]) -> None:
        """Process a single statement node."""
        sid = row["sid"]
        code = row["code"]
        node_type = row["node_type_id"]

        # Ensure feature containers exist
        self.guard_processor.ensure_feat(sid, node_type)
        self.state.node_debug[sid]["code"] = code

        # Reset statement-level tracking
        self.state.exclude_vars_stmt = set()
        self.state.used_by_call_stmt = set()

        # Get original AST node
        orig = self._get_orig_for_stmt(sid)

        # Check for assignment with RHS call
        assign_rhs_has_call = self._check_assignment_rhs_call(node_type, orig)

        # Process based on statement type
        if orig is not None:
            if self._is_statement_level_call(node_type, orig):
                self.call_processor.process_statement_level_call(sid, orig)
            elif self.control_processor.is_control_node(node_type):
                self.control_processor.process_control_node(sid, node_type, orig)
            elif self.declaration_processor.is_declaration(node_type):
                self.declaration_processor.process_declaration(sid, orig)
            elif self._is_assignment(node_type):
                self.assignment_processor.process_assignment(
                    sid, orig, assign_rhs_has_call
                )
            elif self.declaration_processor.is_array_decl(node_type):
                self.declaration_processor.process_array_declaration(sid, orig)
            else:
                self.guard_processor.process_generic_statement(sid, orig)

    def _is_statement_level_call(self, node_type: str, orig: Dict[str, Any]) -> bool:
        """Check if this is a statement-level call node."""
        return (
            node_type in {"UserDefinedCall", "StandardLibCall"}
            and isinstance(orig, dict)
            and orig.get("nodeType") in {"ParameterList", "ArgumentList"}
        )

    def _is_assignment(self, node_type: str) -> bool:
        """Check if this is an assignment node."""
        return node_type == "AssignmentExpression"

    def _check_assignment_rhs_call(
        self, node_type: str, orig: Optional[Dict[str, Any]]
    ) -> bool:
        """Check if assignment RHS contains a call."""
        if node_type != "AssignmentExpression" or not isinstance(orig, dict):
            return False

        kids = orig.get("children") or []
        rhs_node = kids[1] if len(kids) >= 2 else None
        return isinstance(rhs_node, dict) and isinstance(
            self.dfg._find_first_call_node(rhs_node), dict
        )

    def _get_orig_for_stmt(self, sid: int) -> Optional[Dict[str, Any]]:
        """Get original AST node for a statement ID."""
        flat_row = self.dfg._find_ast_row_by_sid(sid)
        if not isinstance(flat_row, dict):
            return None

        orig_id = (
            flat_row.get("orig_id")
            if isinstance(flat_row.get("orig_id"), int)
            else None
        )
        if orig_id is None:
            alt = flat_row.get("id")
            orig_id = alt if isinstance(alt, int) else None

        return self.dfg.id2orig.get(orig_id) if orig_id is not None else None

    def get_processing_state(self) -> ProcessingState:
        """Get the current processing state."""
        return self.state
