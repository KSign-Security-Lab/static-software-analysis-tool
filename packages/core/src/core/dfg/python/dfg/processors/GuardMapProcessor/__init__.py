"""
Guard Map Processor for DFG Extraction

This module handles the complex guard map building logic that analyzes
AST guard edges and propagates guard information to all relevant statements.
"""

from collections import defaultdict, deque
from typing import Any, Dict, List, Tuple


class GuardMapProcessor:
    """Handles guard map building and guard information propagation."""

    def __init__(self, dfg_extractor):
        self.dfg = dfg_extractor

    def build_guard_map(self) -> Dict[int, Dict[str, Dict[str, Any]]]:
        """
        Build guard map from AST guard edges.

        Analyzes AST guard edges to propagate variable-specific guard information
        (lower/upper/upper_const) to all relevant statement IDs.

        Returns:
            gmap: Dict[int, Dict[str, Dict[str, Any]]]
                Each dst_sid -> {
                    <var>: {"kind":int, "lower":0|1, "upper":0|1, "upper_const":float},
                    "*":   {...},  # fallback aggregate
                    "__agg__": {...}  # same as "*"
                }
        """
        # Load AST edges
        ast_res = getattr(self.dfg, "ast_result", {}) or {}
        pc_edges = (
            ast_res.get("edges_ast_pc") or getattr(self.dfg, "edges_ast_pc", []) or []
        )
        sb_edges = (
            ast_res.get("edges_ast_sb") or getattr(self.dfg, "edges_ast_sb", []) or []
        )
        grd_edges = (
            ast_res.get("edges_ast_guard")
            or getattr(self.dfg, "edges_ast_guard", [])
            or []
        )

        # Build idmap if not available
        idmap = self._build_idmap_if_needed()

        # Build adjacency lists
        pc, sb = self._build_adjacency_lists(pc_edges, sb_edges)

        # Get control node types and build sid2type mapping
        sid2type = self._build_sid2type_mapping()

        # Process control flow guards
        cond_guard_by_src = self._process_control_flow_guards(sid2type, idmap)

        # Propagate guards through edges
        gmap = self._propagate_guards(grd_edges, cond_guard_by_src, pc, sb)

        return gmap

    def _build_idmap_if_needed(self) -> Dict[int, Dict[str, Any]]:
        """Build idmap from AST if not available."""
        idmap = getattr(self.dfg, "idmap", None)
        if not isinstance(idmap, dict) or not idmap:
            ast_root = (
                getattr(self.dfg, "ast_json", None)
                or getattr(self.dfg, "ast_result", {}).get("ast_json")
                or getattr(self.dfg, "ast", None)
                or getattr(self.dfg, "ast_result", {}).get("ast")
            )
            if isinstance(ast_root, dict):
                idmap = self._build_idmap_from_ast(ast_root)
                try:
                    self.dfg.idmap = idmap
                except Exception:
                    pass
            else:
                idmap = {}
        return idmap

    def _build_idmap_from_ast(self, root: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
        """Build idmap by walking AST."""
        m = {}

        def walk(n):
            if isinstance(n, dict):
                nid = n.get("id")
                if isinstance(nid, int):
                    m[nid] = n
                for c in n.get("children") or []:
                    walk(c)
            elif isinstance(n, list):
                for c in n:
                    walk(c)

        walk(root)
        return m

    def _build_adjacency_lists(
        self, pc_edges: List, sb_edges: List
    ) -> Tuple[Dict, Dict]:
        """Build PC and SB adjacency lists."""
        pc = defaultdict(list)
        sb = defaultdict(list)

        for edges, adj_list in [(pc_edges, pc), (sb_edges, sb)]:
            for e in edges:
                if isinstance(e, dict):
                    try:
                        src_val = e.get("src")
                        dst_val = e.get("dst")
                        if src_val is None or dst_val is None:
                            continue
                        src, dst = int(src_val), int(dst_val)
                    except Exception:
                        continue
                elif isinstance(e, (list, tuple)) and len(e) >= 2:
                    try:
                        src, dst = int(e[0]), int(e[1])
                    except Exception:
                        continue
                else:
                    continue
                adj_list[src].append(dst)

        return pc, sb

    def _build_sid2type_mapping(self) -> Dict[int, str]:
        """Build mapping from sid to node type."""
        sid2type = {}
        for r in getattr(self.dfg, "nodes", []):
            sid2type[r.get("sid")] = r.get("node_type_id") or r.get("node_type")
        return sid2type

    def _process_control_flow_guards(
        self, sid2type: Dict[int, str], idmap: Dict[int, Dict[str, Any]]
    ) -> Dict[int, Dict[str, Dict[str, Any]]]:
        """Process control flow guards from if/for/while statements."""
        CONTROL = {
            "IfStatement",
            "ForStatement",
            "WhileStatement",
            "DoWhileStatement",
            "DoStatement",
        }

        cond_guard_by_src = {}

        for sid, nt in sid2type.items():
            if nt not in CONTROL:
                continue

            ast_node = self._get_orig_ast_for_sid(sid, idmap)
            if not isinstance(ast_node, dict):
                continue

            # Get condition AST
            try:
                cond_ast = self.dfg._get_condition_node(nt, ast_node)
            except Exception:
                cond_ast = self._get_cond_ast_fallback(nt, ast_node)

            # Parse guards from condition
            parsed = {}
            if cond_ast is not None:
                try:
                    parsed = self.dfg._guards_from_condition_ast(cond_ast) or {}
                except Exception:
                    parsed = {}

            # Normalize guard data
            norm = {}
            for v, g in parsed.items() if isinstance(parsed, dict) else []:
                if not v:
                    continue
                try:
                    norm[v] = {
                        "lower": int(g.get("lower", 0)),
                        "upper": int(g.get("upper", 0)),
                        "upper_const": float(g.get("upper_const", 0.0)),
                    }
                except Exception:
                    norm[v] = {"lower": 0, "upper": 0, "upper_const": 0.0}

            # Add ForStatement header guards
            if nt == "ForStatement":
                try:
                    extra = self.dfg._guards_from_for_header(ast_node) or {}
                    for v, g in extra.items():
                        e = norm.setdefault(
                            v, {"lower": 0, "upper": 0, "upper_const": 0.0}
                        )
                        e["lower"] = max(e["lower"], int(g.get("lower", 0)))
                except Exception:
                    pass

            cond_guard_by_src[sid] = norm

        return cond_guard_by_src

    def _get_orig_ast_for_sid(
        self, sid: int, idmap: Dict[int, Dict[str, Any]]
    ) -> Dict[str, Any] | None:
        """Get original AST node for a sid."""
        # Try sid2flat first
        sid2flat = getattr(self.dfg, "sid2flat", None)
        if isinstance(sid2flat, dict):
            row = sid2flat.get(sid) or {}
            oid = row.get("orig_id")
            if isinstance(oid, int):
                return idmap.get(oid)

        # Try ast_result["nodes"]
        ast_res = getattr(self.dfg, "ast_result", {})
        ast_nodes_list = ast_res.get("nodes") or []
        for r in ast_nodes_list:
            try:
                if int(r.get("sid")) == sid:
                    oid = r.get("orig_id")
                    if isinstance(oid, int):
                        return idmap.get(oid)
            except Exception:
                continue

        # Try self.nodes
        for r in getattr(self.dfg, "nodes", []):
            try:
                sid_val = r.get("sid")
                if sid_val is not None and int(sid_val) == sid:
                    oid = r.get("orig_id")
                    if isinstance(oid, int):
                        return idmap.get(oid)
            except Exception:
                continue

        return None

    def _get_cond_ast_fallback(
        self, nt: str, ast_node: Dict[str, Any]
    ) -> Dict[str, Any] | None:
        """Fallback method to get condition AST."""
        kids = (ast_node.get("children") or []) if isinstance(ast_node, dict) else []
        if nt == "IfStatement":
            return kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
        if nt == "ForStatement":
            return kids[1] if len(kids) >= 2 and isinstance(kids[1], dict) else None
        if nt == "WhileStatement":
            return kids[0] if len(kids) >= 1 and isinstance(kids[0], dict) else None
        if nt in {"DoWhileStatement", "DoStatement"}:
            for k in reversed(kids):
                if isinstance(k, dict) and k.get("nodeType") != "CompoundStatement":
                    return k
            return None
        return None

    def _propagate_guards(
        self, grd_edges: List, cond_guard_by_src: Dict, pc: Dict, sb: Dict
    ) -> Dict[int, Dict[str, Dict[str, Any]]]:
        """Propagate guards through guard edges."""
        gmap = defaultdict(dict)

        def _merge_agg(dst_cur: dict, add: dict, kind: int):
            cur = dst_cur or {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0}
            cur["kind"] = cur.get("kind", 0) or kind
            try:
                cur["lower"] = max(int(cur.get("lower", 0)), int(add.get("lower", 0)))
                cur["upper"] = max(int(cur.get("upper", 0)), int(add.get("upper", 0)))
                cur["upper_const"] = max(
                    float(cur.get("upper_const", 0.0)),
                    float(add.get("upper_const", 0.0)),
                )
            except Exception:
                pass
            return cur

        for ge in grd_edges:
            # Parse guard edge
            if isinstance(ge, dict):
                try:
                    src_sid = int(ge.get("src", -1))
                    dst_first = int(ge.get("dst", -1))
                    kind = int(ge.get("guard_kind", 0))
                except Exception:
                    continue
                branch = ge.get("guard_branch", None)
            elif (
                isinstance(ge, (list, tuple))
                and len(ge) >= 3
                and isinstance(ge[2], dict)
            ):
                try:
                    src_sid = int(ge[0])
                    dst_first = int(ge[1])
                except Exception:
                    continue
                feat = ge[2].get("feat", {}) if isinstance(ge[2], dict) else {}
                kind = int(
                    (feat.get("guard_kind") if isinstance(feat, dict) else 0) or 0
                )
                branch = None
            else:
                continue

            if kind not in (1, 2, 4):
                continue

            # Select variable guards
            var_g = {}
            if kind == 1:  # If
                if branch == 0:  # then
                    var_g = cond_guard_by_src.get(src_sid, {}) or {}
                else:
                    var_g = {}
            elif kind == 2:  # Loop
                var_g = cond_guard_by_src.get(src_sid, {}) or {}
            else:  # Switch
                var_g = {}

            # Aggregate guards
            agg = {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0}
            for g in var_g.values():
                try:
                    agg["lower"] |= int(g.get("lower", 0))
                    agg["upper"] |= int(g.get("upper", 0))
                    uc = float(g.get("upper_const", 0.0))
                    if uc > agg["upper_const"]:
                        agg["upper_const"] = uc
                except Exception:
                    pass

            # Propagate through SB + PC
            q = deque([dst_first])
            seen = set()
            while q:
                u = q.popleft()
                if u in seen:
                    continue
                seen.add(u)

                entry = gmap.setdefault(u, {})

                # Merge variable guards
                for v, g in var_g.items():
                    cur = entry.get(
                        v, {"kind": kind, "lower": 0, "upper": 0, "upper_const": 0.0}
                    )
                    if not cur.get("kind"):
                        cur["kind"] = kind
                    try:
                        cur["lower"] |= int(g.get("lower", 0))
                        cur["upper"] |= int(g.get("upper", 0))
                        cur["upper_const"] = max(
                            float(cur.get("upper_const", 0.0)),
                            float(g.get("upper_const", 0.0)),
                        )
                    except Exception:
                        pass
                    entry[v] = cur

                # Fallback ("*", "__agg__")
                entry["*"] = _merge_agg(entry.get("*") or {}, agg, kind)
                entry["__agg__"] = entry["*"]

                # Expand
                for v in sb.get(u, []):
                    if v not in seen:
                        q.append(v)
                for v in pc.get(u, []):
                    if v not in seen:
                        q.append(v)

        return gmap
