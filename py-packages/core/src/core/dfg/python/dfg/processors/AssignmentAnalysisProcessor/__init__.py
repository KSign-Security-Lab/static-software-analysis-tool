"""
Assignment Analysis Processor for DFG Extraction

This module handles detailed assignment analysis including
declaration initialization detection and assignment AST processing.
"""

import re
from typing import Any, Dict, List, Set, Tuple

from dfg.constants import KEYWORDS


class AssignmentAnalysisProcessor:
    """Handles detailed assignment analysis and related utilities."""

    def __init__(self, dfg_extractor):
        self.dfg = dfg_extractor

    def is_decl_init_trick(
        self, sid: int, name: str, assign_node: Dict[str, Any]
    ) -> bool:
        """
        Detect declaration initialization bundles.
        Checks for patterns like name[...] = { (array brace initialization) or
        name[...] = "..." (string literal initialization) and verifies that
        the previous 1-2 flattened nodes are ArrayDeclaration/ArraySizeAllocation
        with the same name (bundle structure complement).
        """
        code = assign_node.get("code") or ""
        if not name or not code:
            return False

        # Pattern: name[ ... ] = { ... }  or  name[ ... ] = "..."
        pat_brace = r"^\s*" + re.escape(name) + r"\s*\[[^\]]+\]\s*=\s*\{"
        pat_str = r"^\s*" + re.escape(name) + r"\s*\[[^\]]+\]\s*=\s*\""
        if re.search(pat_brace, code) or re.search(pat_str, code):
            return True

        # Check adjacent flattened nodes (ArrayDecl/ArraySizeAlloc + same name)
        idx = None
        for i, n in enumerate(self.dfg.nodes):
            if n["sid"] == sid:
                idx = i
                break
        if idx is None:
            return False

        def _name_from_orig(row_sid: int) -> str:
            flat = self.dfg._find_ast_row_by_sid(row_sid)
            orig = self.dfg._orig_for_stmt(flat)
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
                nt = self.dfg.nodes[j]["node_type_id"]
                if nt in {"ArrayDeclaration", "ArraySizeAllocation"}:
                    if _name_from_orig(self.dfg.nodes[j]["sid"]) == name:
                        return True
        return False

    def assignment_by_ast(
        self, assign_node: Dict[str, Any], cur_sid: int
    ) -> Tuple[List[str], List[Tuple[str, str]], int, int]:
        """
        AssignmentExpression specific: (def_vars, uses[(var,role)], is_buffer_access, is_sink)
        """
        def_vars: List[str] = []
        uses: List[Tuple[str, str]] = []
        iba, is_sink = 0, 0
        kids = assign_node.get("children", []) or []
        lhs = kids[0] if len(kids) >= 1 else None
        rhs = kids[1] if len(kids) >= 2 else None
        base_name: str = ""

        # Helper: LHS text-based indexing detection
        def _lhs_textual_indexing(node: Dict[str, Any], name: str) -> Tuple[bool, bool]:
            """
            Detect 'name[ ... ]' pattern in code string on the left side of '='.
            Returns: (has_indexing, index_has_identifier_for_sink)
            - has_indexing: True if LHS has subscript
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
            # Remove sizeof(...) chunks and check for identifier existence → sink detection only
            idx_no_sizeof = re.sub(r"\bsizeof\s*\([^)]*\)", "", idx_expr)
            has_ident = bool(re.search(r"[A-Za-z_]\w*", idx_no_sizeof))
            return (True, has_ident)

        if isinstance(lhs, dict) and lhs.get("nodeType") == "ArraySubscriptExpression":
            base, index = (lhs.get("children") or [None, None])[:2]

            # LHS base = USE(address calculation), not DEF
            if isinstance(base, dict):
                base_full = self.dfg._fullname_from_expr(base)
                if base_full and base_full not in KEYWORDS:
                    uses.append((base_full, "base"))

            # index USE
            has_runtime_index = False
            if isinstance(index, dict):
                # 1) Collect USE for debugging/edge generation including sizeof(...) internals
                for t in self.dfg._idents_from_ast_node(
                    index, skip_sizeof=False, skip_callee=True
                ):
                    if t and t not in KEYWORDS:
                        uses.append((t, "index"))

                # 2) Sink determination by 'runtime identifier' existence (exclude sizeof internal identifiers)
                for t in self.dfg._idents_from_ast_node(
                    index, skip_sizeof=True, skip_callee=True
                ):
                    if t and t not in KEYWORDS:
                        has_runtime_index = True
                        break

            iba = 1
            is_sink = (
                1 if has_runtime_index else 0
            )  # Only when index contains runtime identifiers

        elif isinstance(lhs, dict) and lhs.get("nodeType") == "Identifier":
            base_name = lhs.get("name") or ""
            if isinstance(base_name, str) and base_name and base_name not in KEYWORDS:
                def_vars.append(base_name)
                _has_idx, _idx_has_ident = _lhs_textual_indexing(assign_node, base_name)
                if _has_idx:
                    # Don't treat as runtime access if it's a declaration initialization bundle
                    if not self.is_decl_init_trick(cur_sid, base_name, assign_node):
                        iba = 1
                        if _idx_has_ident:
                            is_sink = 1

        else:
            # Other LHS expressions: conservative DEF processing with first identifier
            ids = self.dfg._idents_from_ast_node(
                lhs, skip_sizeof=True, skip_callee=True
            )
            if ids:
                def_vars.append(ids[0])

        # RHS analysis: first index(role=index) and base(role=base), then value(exclude duplicates/index)
        rhs_index_vars: Set[str] = set()
        if isinstance(rhs, dict) and rhs.get("nodeType") == "ArraySubscriptExpression":
            rk = rhs.get("children") or []
            rhs_base = rk[0] if len(rk) > 0 else None
            rhs_index = rk[1] if len(rk) > 1 else None

            # base USE (read)
            if isinstance(rhs_base, dict):
                rhs_base_full = self.dfg._fullname_from_expr(rhs_base)
                if rhs_base_full and rhs_base_full not in KEYWORDS:
                    uses.append((rhs_base_full, "base"))

            # index USE
            if isinstance(rhs_index, dict):
                for t in self.dfg._idents_from_ast_node(
                    rhs_index, skip_sizeof=False, skip_callee=True
                ):
                    if t and t not in KEYWORDS:
                        uses.append((t, "index"))
                        rhs_index_vars.add(t)
        elif isinstance(rhs, dict) and rhs.get("nodeType") == "Identifier":
            # Simple identifier RHS - treat as value USE
            rhs_name = rhs.get("name")
            if isinstance(rhs_name, str) and rhs_name and rhs_name not in KEYWORDS:
                uses.append((rhs_name, "value"))
        else:
            # Other RHS expressions - collect all identifiers as value USEs
            for t in self.dfg._idents_from_ast_node(
                rhs, skip_sizeof=True, skip_callee=True
            ):
                if t and t not in KEYWORDS:
                    uses.append((t, "value"))

        return def_vars, uses, iba, is_sink

    def array_decl_by_ast(
        self, decl: Dict[str, Any]
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        ArrayDeclaration / ArraySizeAllocation processing:
        - def_vars: array identifier
        - uses: identifiers from length expression (but sizeof(...) internals are not counted as USE)
        """
        def_vars: List[str] = []
        uses: List[Tuple[str, str]] = []

        nt = decl.get("nodeType")
        if nt == "ArrayDeclaration":
            nm = decl.get("name")
            if isinstance(nm, str) and nm and nm not in KEYWORDS:
                def_vars.append(nm)
            # Extract length expression (varies by schema, e.g., children[0])
            kids = decl.get("children") or []
            length = kids[0] if kids else None
            if isinstance(length, dict):
                # ✅ sizeof internals are not counted as USE
                for t in self.dfg._idents_from_ast_node(
                    length, skip_sizeof=True, skip_callee=True
                ):
                    if t and t not in KEYWORDS:
                        uses.append((t, "size"))
        elif nt == "ArraySizeAllocation":
            # Apply same rules if needed
            kids = decl.get("children") or []
            length = kids[0] if kids else None
            if isinstance(length, dict):
                for t in self.dfg._idents_from_ast_node(
                    length, skip_sizeof=True, skip_callee=True
                ):
                    if t and t not in KEYWORDS:
                        uses.append((t, "size"))

        return def_vars, uses
