"""
Initialization Processor for DFG Extraction

This module handles the initialization and setup of the DFG extractor,
including AST processing, node creation, and data structure preparation.
"""

from typing import Any, Dict, List, Set, Tuple


class InitializationProcessor:
    """Handles DFG initialization and setup."""

    def __init__(self, dfg_extractor):
        self.dfg = dfg_extractor

    def initialize_dfg(
        self, ast_json: Dict[str, Any], ast_result: Dict[str, Any], sink_mode: str
    ) -> None:
        """Initialize the DFG extractor with AST data."""
        # Store basic data
        self.dfg.ast_json = ast_json
        self.dfg.ast_result = ast_result or {}
        self.dfg.ast_nodes = ast_result.get("nodes", [])
        self.dfg.ast_guard = ast_result.get("edges_ast_guard", [])
        self.dfg.sink_mode = sink_mode

        # Build sid2flat mapping
        self._build_sid2flat_mapping()

        # Build AST index and parameter names
        self.dfg.id2orig = self.dfg._index_ast_by_id(ast_json)
        self.dfg.param_names = self.dfg._collect_param_names(ast_json)

        # Initialize DFG nodes
        self._initialize_dfg_nodes()

        # Initialize additional attributes for compatibility
        self._initialize_compatibility_attributes()

    def _build_sid2flat_mapping(self) -> None:
        """Build mapping from sid to flattened AST row."""
        self.dfg.sid2flat = {}
        for _row in self.dfg.ast_nodes:
            try:
                _sid = int(_row.get("sid"))
            except Exception:
                continue
            self.dfg.sid2flat[_sid] = _row

    def _initialize_dfg_nodes(self) -> None:
        """Initialize DFG nodes from AST nodes."""
        self.dfg.nodes = []
        self.dfg.edges_defuse = []
        self.dfg.edges = []

        for n in self.dfg.ast_nodes:
            sid = int(n.get("sid"))
            code = n.get("code") or ""
            node_type = n.get("node_type_id") or n.get("node_type") or ""

            self.dfg.nodes.append(
                {
                    "sid": sid,
                    "code": code,
                    "node_type_id": node_type,
                    # Additional fields will be populated during processing
                }
            )

    def _initialize_compatibility_attributes(self) -> None:
        """Initialize additional attributes for compatibility."""
        # dst SID 기준 가드 주입을 위해 (sid→feat) 캐시
        self.dfg._sid2feat = {
            int(r.get("sid")): (r.get("feat") or {})
            for r in self.dfg.ast_nodes
            if "sid" in r
        }

        # Additional attributes for compatibility
        self.dfg.orig2sid = {}
        self.dfg.sb_edges = set()
        self.dfg.idmap = {}
        # id2orig is already set above, don't overwrite it
