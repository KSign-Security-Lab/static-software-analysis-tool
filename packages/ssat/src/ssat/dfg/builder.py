"""DFG Builder for creating Data Flow Graphs from CPG, AST, and Template data."""

import json
import re
from typing import Any, Dict, List, Optional, Set

from ..types.ast import IASTNode, IASTResult
from ..types.cpg import CPGRoot, VertexGeneric
from ..types.dfg import FlowType, GuardType, IDFGEdge, IDFGEdgeFeature, IDFGGraph, IDFGNode, IDFGNodeFeature
from ..types.node import TemplateNodes
from ..types.template.BaseNode.base_types import TemplateNodeTypes

EMPTY_NODE_FEATURE: IDFGNodeFeature = {
    "nodeType": TemplateNodeTypes.UNKNOWN,
    "inDegreeDFG": 0,
    "outDegreeDFG": 0,
    "defCount": 0,
    "useCount": 0,
    "isBufferAccess": False,
    "isSinkAssignment": False,
    "isSinkCallUnbounded": False,
    "isSinkCallBounded": False,
    "callDestinationIndexed": False,
    "callLengthLinkedToDestination": False,
    "callSizeNonConstant": False,
    "callDangerUnbounded": False,
}


class DFGBuilder:
    """Builder for Data Flow Graphs."""

    def __init__(self, cpg: CPGRoot, ast: IASTResult, template: TemplateNodes):
        """Initialize DFG builder."""
        self.cpg = cpg
        self.ast = ast
        self.template = template

    def build_dfg_from_cpg(self) -> IDFGGraph:
        """Build DFG from CPG data."""
        nodes = self._build_nodes()
        edges = self._build_edges()

        child_to_ancestor = self._create_edge_redirection_map(self.ast["nodes"], self.template)
        synced_dfg_nodes = self._sync_dfg_nodes_with_ast_nodes(nodes, self.ast["nodes"], child_to_ancestor)
        redirected_edges = self._redirect_edges_by_redirection_map(edges, child_to_ancestor)

        self._update_node_degrees(synced_dfg_nodes, redirected_edges)
        unique_edges = self._filter_identical_edges(redirected_edges)
        return {"nodes": synced_dfg_nodes, "edges": unique_edges}

    def _build_nodes(self) -> List[IDFGNode]:
        """Build DFG nodes from CPG vertices."""
        by_id: Dict[int, IDFGNode] = {}

        edges = self.cpg.get("export", {}).get("@value", {}).get("edges", [])
        ref_edges = [e for e in edges if e.get("label") == "REF"]
        allowed_decl = {"LOCAL", "MEMBER", "METHOD_PARAMETER_IN", "METHOD_PARAMETER_OUT", "PARAMETER", "PARAMETER_IN", "PARAMETER_OUT"}

        def get_or_create(v: VertexGeneric) -> IDFGNode:
            """Get or create DFG node from vertex."""
            v_id = self._unwrap_value(v.get("id", {}))
            if v_id in by_id:
                return by_id[v_id]

            node: IDFGNode = {
                "sid": -999,  # will be filled from AST if available
                "id": v_id,
                "features": EMPTY_NODE_FEATURE.copy(),
                "debug": {
                    "label": self._get_label(v),
                    "name": self._get_name(v) or self._get_code(v) or "<unnamed>",
                    "line": self._get_line_number(v),
                },
            }
            by_id[v_id] = node
            return node

        # Collect candidate vertices and count defs/uses
        for ref in ref_edges:
            use_id = self._unwrap_value(ref.get("outV", {}))
            def_id = self._unwrap_value(ref.get("inV", {}))
            use = self._get_node_by_id(use_id)
            def_node = self._get_node_by_id(def_id)
            if not use or not def_node:
                continue
            if self._get_label(use) != "IDENTIFIER":
                continue
            if self._get_label(def_node) not in allowed_decl:
                continue

            use_node = get_or_create(use)
            def_node_obj = get_or_create(def_node)

            use_node["features"]["useCount"] += 1
            def_node_obj["features"]["defCount"] += 1

        # Compute full feature set per node
        for node in by_id.values():
            counted_def = node["features"]["defCount"]
            counted_use = node["features"]["useCount"]
            base = self._compute_node_feature(node["id"])
            node["features"] = {
                **base,
                "defCount": counted_def,
                "useCount": counted_use,
                "inDegreeDFG": 0,
                "outDegreeDFG": 0,
            }

        return list(by_id.values())

    def _build_edges(self) -> List[IDFGEdge]:
        """Build DFG edges from CPG REF edges."""
        edges: List[IDFGEdge] = []

        cpg_edges = self.cpg.get("export", {}).get("@value", {}).get("edges", [])
        ref_edges = [e for e in cpg_edges if e.get("label") == "REF"]
        allowed_decl = {"LOCAL", "MEMBER", "METHOD_PARAMETER_IN", "METHOD_PARAMETER_OUT", "PARAMETER", "PARAMETER_IN", "PARAMETER_OUT"}

        for ref in ref_edges:
            use_id = self._unwrap_value(ref.get("outV", {}))
            def_id = self._unwrap_value(ref.get("inV", {}))
            use = self._get_node_by_id(use_id)
            def_node = self._get_node_by_id(def_id)
            if not use or not def_node:
                continue
            if self._get_label(use) != "IDENTIFIER":
                continue
            if self._get_label(def_node) not in allowed_decl:
                continue

            feat = self._compute_edge_feature(def_node, use)
            edge: IDFGEdge = {
                "source": def_id,
                "destination": use_id,
                "features": feat,
                "debug": {
                    "var": self._get_name(use) or self._get_code(use),
                    "srcLine": self._get_line_number(def_node),
                    "dstLine": self._get_line_number(use),
                },
            }
            edges.append(edge)

        return edges

    def _sync_dfg_nodes_with_ast_nodes(
        self, dfg_nodes: List[IDFGNode], ast_nodes: List[IASTNode], child_to_ancestor: Dict[int, int]
    ) -> List[IDFGNode]:
        """Sync DFG nodes with AST nodes."""
        synced_nodes: List[IDFGNode] = []
        parent_to_children: Dict[int, List[int]] = {}
        for child, parent in child_to_ancestor.items():
            if parent not in parent_to_children:
                parent_to_children[parent] = []
            parent_to_children[parent].append(child)

        for ast_node in ast_nodes:
            orig_id = ast_node.get("orig_id", 0)
            matching_dfg_node = next((n for n in dfg_nodes if ast_node.get("orig_id") == n["id"]), None)
            if matching_dfg_node:
                matching_dfg_node["sid"] = ast_node.get("sid", -999)
            else:
                node = self._get_node_by_id(orig_id)
                if not node:
                    matching_dfg_node = {
                        "sid": ast_node.get("sid", -999),
                        "id": orig_id,
                        "features": EMPTY_NODE_FEATURE.copy(),
                        "debug": {"label": "<node>", "name": "<unnamed>", "line": None, "info": "No matching DFG node found for AST node"},
                    }
                else:
                    matching_dfg_node = {
                        "sid": ast_node.get("sid", -999),
                        "id": orig_id,
                        "features": EMPTY_NODE_FEATURE.copy(),
                        "debug": {
                            "label": self._get_label(node),
                            "name": self._get_name(node),
                            "line": self._get_line_number(node),
                            "info": "No matching DFG node found for AST node",
                        },
                    }

            # Aggregate features from children
            children_ids = parent_to_children.get(matching_dfg_node["id"], [])
            for parent_id in children_ids:
                parent_dfg_node = next((n for n in dfg_nodes if n["id"] == parent_id), None)
                if not parent_dfg_node:
                    continue
                for child_id in parent_to_children.get(parent_id, []):
                    if child_id == matching_dfg_node["id"]:
                        continue
                    child_dfg_node = next((n for n in dfg_nodes if n["id"] == child_id), None)
                    if not child_dfg_node:
                        continue
                    parent_dfg_node["features"]["outDegreeDFG"] += child_dfg_node["features"]["outDegreeDFG"]
                    parent_dfg_node["features"]["inDegreeDFG"] += child_dfg_node["features"]["inDegreeDFG"]
                    parent_dfg_node["features"]["defCount"] += child_dfg_node["features"]["defCount"]
                    parent_dfg_node["features"]["useCount"] += child_dfg_node["features"]["useCount"]
                    parent_dfg_node["features"]["isBufferAccess"] = parent_dfg_node["features"]["isBufferAccess"] or child_dfg_node["features"]["isBufferAccess"]
                    parent_dfg_node["features"]["isSinkAssignment"] = parent_dfg_node["features"]["isSinkAssignment"] or child_dfg_node["features"]["isSinkAssignment"]
                    parent_dfg_node["features"]["isSinkCallUnbounded"] = parent_dfg_node["features"]["isSinkCallUnbounded"] or child_dfg_node["features"]["isSinkCallUnbounded"]
                    parent_dfg_node["features"]["isSinkCallBounded"] = parent_dfg_node["features"]["isSinkCallBounded"] or child_dfg_node["features"]["isSinkCallBounded"]
                    parent_dfg_node["features"]["callDestinationIndexed"] = parent_dfg_node["features"]["callDestinationIndexed"] or child_dfg_node["features"]["callDestinationIndexed"]
                    parent_dfg_node["features"]["callLengthLinkedToDestination"] = parent_dfg_node["features"]["callLengthLinkedToDestination"] or child_dfg_node["features"]["callLengthLinkedToDestination"]
                    parent_dfg_node["features"]["callSizeNonConstant"] = parent_dfg_node["features"]["callSizeNonConstant"] or child_dfg_node["features"]["callSizeNonConstant"]
                    parent_dfg_node["features"]["callDangerUnbounded"] = parent_dfg_node["features"]["callDangerUnbounded"] or child_dfg_node["features"]["callDangerUnbounded"]

            synced_nodes.append(matching_dfg_node)

        return synced_nodes

    def _create_edge_redirection_map(self, ast_nodes: List[IASTNode], template: TemplateNodes) -> Dict[int, int]:
        """Create edge redirection map from AST nodes and template."""
        selected = {node.get("orig_id", 0) for node in ast_nodes}
        child_to_ancestor: Dict[int, int] = {}

        def dfs(node: TemplateNodes, current_ancestor: Optional[int]) -> None:
            """DFS to build redirection map."""
            node_id = node.get("id", 0) if isinstance(node, dict) else getattr(node, "id", 0)
            is_selected = node_id in selected
            next_ancestor = node_id if is_selected else current_ancestor

            # If node is NOT selected but we have a selected ancestor, map this node to that ancestor
            if not is_selected and next_ancestor is not None:
                child_to_ancestor[node_id] = next_ancestor

            children = node.get("children", []) if isinstance(node, dict) else getattr(node, "children", [])
            for ch in children:
                dfs(ch, next_ancestor)

        dfs(template, None)
        return child_to_ancestor

    def _redirect_edges_by_redirection_map(self, dfg_edges: List[IDFGEdge], child_to_ancestor: Dict[int, int]) -> List[IDFGEdge]:
        """Redirect edges using redirection map."""
        out: List[IDFGEdge] = []
        for e in dfg_edges:
            new_source = child_to_ancestor.get(e["source"], e["source"])
            new_destination = child_to_ancestor.get(e["destination"], e["destination"])

            if new_source == new_destination:
                continue

            out.append({
                "source": new_source,
                "destination": new_destination,
                "features": e["features"],
                "debug": e.get("debug"),
            })
        return out

    def _filter_identical_edges(self, edges: List[IDFGEdge]) -> List[IDFGEdge]:
        """Filter identical edges."""
        unique_objects_set = {json.dumps(obj, sort_keys=True) for obj in edges}
        unique_array = [json.loads(s) for s in unique_objects_set]
        return unique_array  # type: ignore

    def _compute_node_feature(self, cpg_id: int) -> IDFGNodeFeature:
        """Compute node feature from CPG vertex."""
        f = EMPTY_NODE_FEATURE.copy()
        v = self._get_node_by_id(cpg_id)
        if not v:
            return f

        f["nodeType"] = self._infer_template_type(v)

        parents = [self._get_node_by_id(pid) for pid in self._get_ast_parents(cpg_id)]
        parents = [p for p in parents if p is not None]

        is_array_index_context = any(self._get_label(p) == "CALL" and re.search(r"\[.+\]", self._get_code(p) or "") for p in parents)
        is_pointer_deref = any(("*(" in (self._get_code(p) or "")) or ("->" in (self._get_code(p) or "")) for p in parents)
        f["isBufferAccess"] = is_array_index_context or is_pointer_deref

        is_assignment = any("=" in (self._get_code(p) or "") for p in parents)
        f["isSinkAssignment"] = is_assignment and f["isBufferAccess"]

        call_anc = self._nearest_call_ancestor(v)
        if call_anc:
            callee = (self._get_name(call_anc) or self._get_code(call_anc) or "").lower()
            code = (self._get_code(call_anc) or "").lower()

            unbounded = bool(re.search(r"(strcpy|stpcpy|gets|sprintf|vsprintf)\b", callee)) or bool(re.search(r"(strcpy|gets|sprintf)", code))
            bounded = bool(re.search(r"(strncpy|strlcpy|snprintf|vsnprintf|memcpy|memmove|fgets)\b", callee)) or bool(re.search(r"(snprintf|strncpy|memcpy|memmove|fgets)", code))

            f["isSinkCallUnbounded"] = unbounded and not bounded
            f["isSinkCallBounded"] = bounded

            code_parts = code.split(",")
            f["callDestinationIndexed"] = bool(re.search(r"\[[^\]]+\]", code_parts[0] if code_parts else ""))
            f["callLengthLinkedToDestination"] = bool(re.search(r"\b(sizeof|strlen)\s*\(", code))
            f["callSizeNonConstant"] = bool(re.search(r"\b(snprintf|vsnprintf|memcpy|memmove|strncpy)\b", callee)) and not bool(re.search(r"\b\d+\b", code))
            f["callDangerUnbounded"] = bool(re.search(r"\b(gets|strcpy|sprintf)\b", callee))

        return f

    def _compute_edge_feature(self, def_node: VertexGeneric, use: VertexGeneric) -> IDFGEdgeFeature:
        """Compute edge feature."""
        flow = self._classify_flow(def_node, use)
        guard_info = self._find_nearest_guard(use)
        has_lower_guard = self._has_lower_bound_check(use)
        has_upper_guard = self._has_upper_bound_check(use)
        upper_guard_normalization = self._upper_bound_normalization_factor(use)

        return {
            "flow": flow,
            "guard": guard_info["kind"],
            "hasLowerGuard": has_lower_guard,
            "hasUpperGuard": has_upper_guard,
            "upperGuardNormalization": upper_guard_normalization,
        }

    def _classify_flow(self, def_node: VertexGeneric, use: VertexGeneric) -> FlowType:
        """Classify flow type."""
        name = (self._get_name(use) or self._get_code(use) or "").strip()

        # Gather ancestor codes for structural checks
        start_id = self._unwrap_value(use.get("id", {}))
        visited: Set[int] = {start_id}
        q: List[int] = [start_id]
        ancestor_codes: List[str] = []
        hops = 0
        while q and hops < 12:
            cur = q.pop(0) if q else None
            if cur is None:
                break
            for pid in self._get_ast_parents(cur):
                if pid in visited:
                    continue
                visited.add(pid)
                p = self._get_node_by_id(pid)
                if not p:
                    continue
                c = self._get_code(p)
                if c:
                    ancestor_codes.append(c)
                q.append(pid)
            hops += 1

        def any_ancestor_matches(pattern: str) -> bool:
            """Check if any ancestor matches pattern."""
            return any(re.search(pattern, c) for c in ancestor_codes)

        def any_ancestor_includes(s: str) -> bool:
            """Check if any ancestor includes string."""
            return any(s in c for c in ancestor_codes)

        # 1) Array and pointer contexts
        name_esc = self._escape_re(name)
        index_in_brackets_re = re.compile(rf"\[[^\]]*\b{name_esc}\b[^\]]*\]")
        if any(index_in_brackets_re.search(c) for c in ancestor_codes):
            return FlowType.INDEX

        base_before_bracket_re = re.compile(rf"\b{name_esc}\s*\[")
        if any(base_before_bracket_re.search(c) for c in ancestor_codes):
            return FlowType.BASE

        deref_with_name = next(
            (c for c in ancestor_codes if re.search(r"\*\s*\([^)]*\)", c) and re.search(rf"\(.*\b{name_esc}\b.*\)", c)),
            None,
        )
        if deref_with_name:
            base_side_re = re.compile(rf"\*\s*\(\s*{name_esc}\s*[+-]")
            index_side_re = re.compile(rf"[+-]\s*{name_esc}\s*\)")
            if base_side_re.search(deref_with_name):
                return FlowType.BASE
            if index_side_re.search(deref_with_name):
                return FlowType.INDEX
            return FlowType.BASE

        # 2) Call context
        call_anc = self._nearest_call_ancestor(use)
        if call_anc:
            callee = (self._get_name(call_anc) or self._get_code(call_anc) or "").lower()
            call_code = (self._get_code(call_anc) or "").strip()

            # Extract args
            args: List[str] = []
            paren_idx = call_code.find("(")
            last_paren_idx = call_code.rfind(")")
            if paren_idx >= 0 and last_paren_idx > paren_idx:
                inside = call_code[paren_idx + 1 : last_paren_idx]
                args = [s.strip() for s in inside.split(",")]

            arg_index = next((i for i, a in enumerate(args) if re.search(rf"\b{self._escape_re(name)}\b", a)), -1)

            is_in_index_expr = any(re.search(rf"\[[^\]]*\b{self._escape_re(name)}\b[^\]]*\]", a) for a in args)
            if is_in_index_expr:
                return FlowType.INDEX

            # memcpy/memmove
            if re.search(r"\b(memcpy|memmove)\b", callee):
                if arg_index == 0:
                    return FlowType.BASE
                if arg_index == 1:
                    return FlowType.VALUE
                if arg_index == 2:
                    return FlowType.SIZE
            # strncpy/strlcpy/snprintf/vsnprintf
            if re.search(r"\b(strncpy|strlcpy|snprintf|vsnprintf)\b", callee):
                if arg_index == 0:
                    return FlowType.BASE
                if arg_index == 2:
                    return FlowType.SIZE
                if arg_index == 1:
                    return FlowType.VALUE
            # strcpy/stpcpy/sprintf/gets
            if re.search(r"\b(strcpy|stpcpy|sprintf|vsprintf|gets)\b", callee):
                if arg_index == 0:
                    return FlowType.BASE
                if arg_index >= 1:
                    return FlowType.VALUE
            # fgets
            if re.search(r"\b(fgets)\b", callee):
                if arg_index == 0:
                    return FlowType.BASE
                if arg_index == 1:
                    return FlowType.SIZE
                if arg_index == 2:
                    return FlowType.VALUE
            # read/recv/fread
            if re.search(r"\b(read|recv|fread)\b", callee):
                if arg_index == 1:
                    return FlowType.BASE
                if arg_index == 2:
                    return FlowType.SIZE
            # write/send/fwrite
            if re.search(r"\b(write|send|fwrite)\b", callee):
                if arg_index == 1:
                    return FlowType.VALUE
                if arg_index == 2:
                    return FlowType.SIZE
            # allocators
            if re.search(r"\b(malloc|realloc)\b", callee):
                if arg_index >= 0:
                    return FlowType.SIZE
            if re.search(r"\b(calloc)\b", callee):
                if arg_index in [0, 1]:
                    return FlowType.SIZE

        # 3) Predicate/guard context
        pred = self._find_first_predicate_code(use)
        if pred and re.search(r"<|<=|>|>=", pred) and re.search(rf"\b{self._escape_re(name)}\b", pred):
            comp_match = re.search(r"<=|>=|<|>", pred)
            id_pos = pred.find(name)
            comp_pos = comp_match.start() if comp_match else -1
            if comp_pos >= 0 and id_pos >= 0:
                if id_pos < comp_pos:
                    return FlowType.INDEX
                return FlowType.SIZE

        # 4) Direct dereference
        if any_ancestor_includes(f"*{name}") or any_ancestor_includes(f"{name}->") or any_ancestor_includes(f"&{name}["):
            return FlowType.BASE

        # 5) sizeof/alignof/typeof contexts
        if any_ancestor_matches(r"\b(sizeof|alignof|typeof)\s*\("):
            return FlowType.SIZE

        # Default: general value usage
        return FlowType.VALUE

    def _find_nearest_guard(self, n: VertexGeneric) -> Dict[str, GuardType]:
        """Find nearest guard."""
        start = self._unwrap_value(n.get("id", {}))
        visited: Set[int] = {start}
        q: List[int] = [start]

        while q:
            cur = q.pop(0) if q else None
            if cur is None:
                break
            for pid in self._get_ast_parents(cur):
                if pid in visited:
                    continue
                visited.add(pid)
                p = self._get_node_by_id(pid)
                if not p:
                    continue
                lbl = self._get_label(p)
                if lbl == "CONTROL_STRUCTURE":
                    code = (self._get_code(p) or "").strip()
                    if re.match(r"^\s*if\b", code, re.IGNORECASE):
                        return {"kind": GuardType.IF}
                    if re.match(r"^\s*(for|while|do)\b", code, re.IGNORECASE):
                        return {"kind": GuardType.LOOP}
                q.append(pid)

        return {"kind": GuardType.NONE}

    def _has_lower_bound_check(self, n: VertexGeneric) -> bool:
        """Check if node has lower bound check."""
        name = self._get_name(n) or self._get_code(n) or ""
        pattern = re.compile(rf"\b({self._escape_re(name)})\s*>=?\s*0|0\s*<=?\s*({self._escape_re(name)})")
        return self._scan_up_for_predicate(n, pattern)

    def _has_upper_bound_check(self, n: VertexGeneric) -> bool:
        """Check if node has upper bound check."""
        name = self._get_name(n) or self._get_code(n) or ""
        pattern = re.compile(rf"\b({self._escape_re(name)})\s*<\s*[^;]+|\b({self._escape_re(name)})\s*<=\s*[^;]+")
        return self._scan_up_for_predicate(n, pattern)

    def _upper_bound_normalization_factor(self, n: VertexGeneric) -> float:
        """Get upper bound normalization factor."""
        code = self._find_first_predicate_code(n) or ""
        if re.search(r"\bsizeof\s*\(", code):
            return 1.0
        if re.search(r"\b\d+\b", code):
            return 1.0
        return 0.5

    def _scan_up_for_predicate(self, n: VertexGeneric, pattern: re.Pattern) -> bool:
        """Scan up for predicate matching pattern."""
        code = self._find_first_predicate_code(n)
        return bool(code and pattern.search(code))

    def _find_first_predicate_code(self, n: VertexGeneric) -> Optional[str]:
        """Find first predicate code."""
        start = self._unwrap_value(n.get("id", {}))
        visited: Set[int] = {start}
        q: List[int] = [start]

        while q:
            cur = q.pop(0) if q else None
            if cur is None:
                break
            for pid in self._get_ast_parents(cur):
                if pid in visited:
                    continue
                visited.add(pid)
                p = self._get_node_by_id(pid)
                if not p:
                    continue
                if self._get_label(p) == "CONTROL_STRUCTURE":
                    c = self._get_code(p)
                    if c and re.search(r"if|for|while|do", c):
                        return c
                q.append(pid)

        return None

    def _update_node_degrees(self, nodes: List[IDFGNode], edges: List[IDFGEdge]) -> None:
        """Update node degrees."""
        by_id = {n["id"]: n for n in nodes}

        for e in edges:
            src = by_id.get(e["source"])
            dst = by_id.get(e["destination"])
            if src:
                src["features"]["outDegreeDFG"] += 1
            if dst:
                dst["features"]["inDegreeDFG"] += 1

    def _get_node_by_id(self, node_id: int) -> Optional[VertexGeneric]:
        """Get node by ID from CPG."""
        vertices = self.cpg.get("export", {}).get("@value", {}).get("vertices", [])
        for v in vertices:
            if self._unwrap_value(v.get("id", {})) == node_id:
                return v
        return None

    def _get_ast_parents(self, node_id: int) -> List[int]:
        """Get AST parents of a node."""
        out: List[int] = []
        edges = self.cpg.get("export", {}).get("@value", {}).get("edges", [])
        for e in edges:
            if e.get("label") == "AST" and self._unwrap_value(e.get("inV", {})) == node_id:
                out.append(self._unwrap_value(e.get("outV", {})))
        return out

    def _get_ast_children(self, node_id: int) -> List[int]:
        """Get AST children of a node."""
        out: List[int] = []
        edges = self.cpg.get("export", {}).get("@value", {}).get("edges", [])
        for e in edges:
            if e.get("label") == "AST" and self._unwrap_value(e.get("outV", {})) == node_id:
                out.append(self._unwrap_value(e.get("inV", {})))
        return out

    def _get_code(self, node: VertexGeneric) -> Optional[str]:
        """Get CODE property from node."""
        arr = self._read_prop_array(node, "CODE")
        return arr[0] if isinstance(arr, list) and len(arr) > 0 and isinstance(arr[0], str) else None

    def _get_name(self, node: VertexGeneric) -> Optional[str]:
        """Get NAME property from node."""
        arr = self._read_prop_array(node, "NAME")
        return arr[0] if isinstance(arr, list) and len(arr) > 0 and isinstance(arr[0], str) else None

    def _get_label(self, node: VertexGeneric) -> str:
        """Get label from node."""
        label = node.get("label", "")
        return label if isinstance(label, str) else "<node>"

    def _get_line_number(self, node: VertexGeneric) -> Optional[int]:
        """Get line number from node."""
        def num(v: Any) -> Optional[int]:
            """Convert value to number."""
            if isinstance(v, (int, float)):
                return int(v) if v > 0 else None
            if isinstance(v, str):
                try:
                    n = int(v)
                    return n if n > 0 else None
                except ValueError:
                    pass
            if isinstance(v, dict) and "@value" in v:
                return num(v["@value"])
            return None

        def read_loose(n: VertexGeneric, key: str) -> Optional[int]:
            """Read property loosely."""
            props = n.get("properties", {})
            step1 = props.get(key) if isinstance(props, dict) else None

            if step1 and isinstance(step1, dict):
                outer = step1.get("@value")
                if outer and isinstance(outer, dict):
                    inner = outer.get("@value")
                    if isinstance(inner, list) and len(inner) > 0:
                        v = num(inner[0])
                        if v is not None:
                            return v
                v2 = step1.get("@value")
                v2n = num(v2)
                if v2n is not None:
                    return v2n
            v3 = num(step1)
            return v3 if v3 is not None else None

        keys = ["LINE_NUMBER", "START_LINE", "END_LINE", "LINE_NUMBER_END", "LINE"]
        for k in keys:
            v = read_loose(node, k)
            if v is not None:
                return v

        # Try parents and children
        start_id = self._unwrap_value(node.get("id", {}))
        seen: Set[int] = {start_id}

        def try_id(nid: int) -> Optional[int]:
            """Try to get line number from node ID."""
            n = self._get_node_by_id(nid)
            if not n:
                return None
            for k in keys:
                v = read_loose(n, k)
                if v is not None:
                    return v
            return None

        # BFS through parents
        q: List[int] = [start_id]
        while q:
            cur = q.pop(0)
            for pid in self._get_ast_parents(cur):
                if pid in seen:
                    continue
                seen.add(pid)
                v = try_id(pid)
                if v is not None:
                    return v
                q.append(pid)

        # BFS through children
        q = [start_id]
        while q:
            cur = q.pop(0)
            for cid in self._get_ast_children(cur):
                if cid in seen:
                    continue
                seen.add(cid)
                v = try_id(cid)
                if v is not None:
                    return v
                q.append(cid)

        return None

    def _read_prop_array(self, node: VertexGeneric, key: str) -> Optional[List[Any]]:
        """Read property array from node."""
        props = node.get("properties", {})
        if not isinstance(props, dict):
            return None
        step1 = props.get(key)
        if not step1 or not isinstance(step1, dict):
            return None
        outer = step1.get("@value")
        if not outer or not isinstance(outer, dict):
            return None
        inner = outer.get("@value")
        return inner if isinstance(inner, list) else None

    def _nearest_call_ancestor(self, n: VertexGeneric) -> Optional[VertexGeneric]:
        """Find nearest call ancestor."""
        start = self._unwrap_value(n.get("id", {}))
        visited: Set[int] = {start}
        q: List[int] = [start]

        while q:
            cur = q.pop(0) if q else None
            if cur is None:
                break
            for pid in self._get_ast_parents(cur):
                if pid in visited:
                    continue
                visited.add(pid)
                p = self._get_node_by_id(pid)
                if not p:
                    continue
                if self._get_label(p) == "CALL":
                    return p
                q.append(pid)

        return None

    def _infer_template_type(self, v: VertexGeneric) -> TemplateNodeTypes:
        """Infer template type from vertex label."""
        label = self._get_label(v)
        try:
            return TemplateNodeTypes(label)
        except ValueError:
            return TemplateNodeTypes.UNKNOWN

    def _escape_re(self, s: str) -> str:
        """Escape string for regex."""
        return re.escape(s)

    def _unwrap_value(self, x: Any) -> Any:
        """Unwrap GraphSON value."""
        if x is None:
            return None
        if isinstance(x, (str, int, float)):
            return x
        if isinstance(x, dict):
            if "@value" in x:
                inner = x["@value"]
                if isinstance(inner, dict) and "@value" in inner:
                    return inner["@value"]
                return inner
        return None

