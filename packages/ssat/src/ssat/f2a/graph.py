"""Queryable graph views over a Joern CPG (GraphSON) export.

F2-A is specified against abstract "code facts" (call graph, data-flow,
sink index, check patterns, dominance). This module projects those facts
directly out of the CPG the ``ssat cpg`` command produces, exposing the four
graph views the deck talks about:

* **AST** — ``AST`` edges (parent → child); syntax structure, field access, literals.
* **CG**  — ``CALL`` edges (call-site → callee ``METHOD``); who calls whom.
* **DFG** — ``REACHING_DEF`` edges (def → use, intraprocedural) + argument→parameter
            bridging over ``CALL`` edges for interprocedural value flow.
* **CFG/dominance** — ``CFG`` / ``DOMINATE`` edges; "did the check run before the sink".

All edge directions and property shapes here were verified against a real
export (see the F2-A implementation notes).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

# Joern operator call names that model syntax rather than real function calls.
FIELD_ACCESS_OPS = frozenset({"<operator>.indirectFieldAccess", "<operator>.fieldAccess"})
ASSIGNMENT_OPS = frozenset({"<operator>.assignment"})


def _unwrap(value: Any) -> Any:
    """Recursively strip GraphSON ``@value`` wrappers."""
    if isinstance(value, dict) and "@value" in value:
        return _unwrap(value["@value"])
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def cpg_id(vertex: Dict[str, Any]) -> int:
    """The integer id of a raw GraphSON vertex dict."""
    return cast(int, _unwrap(vertex.get("id")))


class CPGModel:
    """Indexed, queryable wrapper around a single CPG GraphSON document."""

    def __init__(self, cpg_json: Any):
        vertices, edges = self._extract_graph(cpg_json)
        self.vertices: List[Dict[str, Any]] = vertices
        self.edges: List[Dict[str, Any]] = edges

        self.by_id: Dict[int, Dict[str, Any]] = {}
        for v in vertices:
            vid = _unwrap(v.get("id"))
            if isinstance(vid, int):
                self.by_id[vid] = v

        # Adjacency indexed by edge label, both directions.
        self._out: Dict[str, Dict[int, List[Tuple[int, Dict[str, Any]]]]] = defaultdict(lambda: defaultdict(list))
        self._in: Dict[str, Dict[int, List[Tuple[int, Dict[str, Any]]]]] = defaultdict(lambda: defaultdict(list))
        # AST parent pointer for climbing to the enclosing method.
        self._ast_parent: Dict[int, int] = {}

        for e in edges:
            label = e.get("label")
            out_v = _unwrap(e.get("outV"))
            in_v = _unwrap(e.get("inV"))
            if not isinstance(label, str):
                continue
            if not isinstance(out_v, int) or not isinstance(in_v, int):
                continue
            self._out[label][out_v].append((in_v, e))
            self._in[label][in_v].append((out_v, e))
            if label == "AST":
                self._ast_parent[in_v] = out_v

        self._filename_by_method = self._build_method_filenames()

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_graph(cpg_json: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Accept a raw export, a ``@value``-wrapped export, or a list of them."""
        vertices: List[Dict[str, Any]] = []
        edges: List[Dict[str, Any]] = []

        def absorb(obj: Any) -> bool:
            if isinstance(obj, dict) and "vertices" in obj and "edges" in obj:
                vertices.extend(obj.get("vertices") or [])
                edges.extend(obj.get("edges") or [])
                return True
            if isinstance(obj, dict) and "@value" in obj:
                return absorb(obj["@value"])
            return False

        if isinstance(cpg_json, list):
            for item in cpg_json:
                absorb(item)
        else:
            absorb(cpg_json)
        return vertices, edges

    def _build_method_filenames(self) -> Dict[int, str]:
        """Map each METHOD id to a source file name."""
        result: Dict[int, str] = {}
        default_file = ""
        for v in self.vertices:
            if v.get("label") == "FILE":
                name = self.scalar(_unwrap(v.get("id")), "NAME")
                if name and name not in ("<includes>", "<unknown>"):
                    default_file = str(name).split("/")[-1]
                    break
        for mid in self.method_ids():
            fn = self.scalar(mid, "FILENAME")
            if fn and fn not in ("<includes>", "<empty>", "<unknown>"):
                result[mid] = str(fn).split("/")[-1]
            else:
                result[mid] = default_file
        return result

    # ------------------------------------------------------------------
    # Property access
    # ------------------------------------------------------------------

    def scalar(self, node_id: Optional[int], key: str) -> Optional[Any]:
        """Return a single property value (unwrapping the VertexProperty→List)."""
        v = self.by_id.get(node_id) if node_id is not None else None
        if not v:
            return None
        prop = v.get("properties", {}).get(key)
        if prop is None:
            return None
        val = _unwrap(prop.get("@value") if isinstance(prop, dict) else prop)
        if isinstance(val, list):
            if len(val) == 1:
                return val[0]
            return val or None
        return val

    def label(self, node_id: Optional[int]) -> str:
        v = self.by_id.get(node_id) if node_id is not None else None
        return v.get("label", "") if v else ""

    def name(self, node_id: Optional[int]) -> str:
        return str(self.scalar(node_id, "NAME") or "")

    def code(self, node_id: Optional[int]) -> str:
        return str(self.scalar(node_id, "CODE") or "")

    def line(self, node_id: Optional[int]) -> Any:
        val = self.scalar(node_id, "LINE_NUMBER")
        return val if val is not None else ""

    def field_name(self, node_id: Optional[int]) -> str:
        return str(self.scalar(node_id, "CANONICAL_NAME") or self.scalar(node_id, "CODE") or "")

    # ------------------------------------------------------------------
    # Adjacency
    # ------------------------------------------------------------------

    def out_ids(self, node_id: int, label: str) -> List[int]:
        return [nid for nid, _ in self._out[label].get(node_id, [])]

    def in_ids(self, node_id: int, label: str) -> List[int]:
        return [nid for nid, _ in self._in[label].get(node_id, [])]

    def out_edges(self, node_id: int, label: str) -> List[Tuple[int, Dict[str, Any]]]:
        return list(self._out[label].get(node_id, []))

    # ------------------------------------------------------------------
    # AST view
    # ------------------------------------------------------------------

    def ast_children(self, node_id: int) -> List[int]:
        return self.out_ids(node_id, "AST")

    def ast_descendants(self, node_id: int) -> Iterable[int]:
        stack = list(self.ast_children(node_id))
        seen = set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            yield cur
            stack.extend(self.ast_children(cur))

    def ast_parent(self, node_id: int) -> Optional[int]:
        """The node's parent in the AST, if it has one."""
        for parent in self.in_ids(node_id, "AST"):
            return parent
        return None

    def is_internal_call(self, call_id: int) -> bool:
        """True if this call-site resolves to a user-defined function with a body.

        Excludes Joern's synthetic operator and global-scope methods, and anything
        marked external -- a call to those tells you nothing about program flow.
        """
        callee = self.call_target(call_id)
        if callee is None:
            return False
        name = self.name(callee)
        if name.startswith("<operator>") or name.startswith("<global>"):
            return False
        return self.scalar(callee, "IS_EXTERNAL") is not True

    def method_of(self, node_id: Optional[int]) -> Optional[int]:
        """Climb AST parents to the enclosing METHOD."""
        cur: Optional[int] = node_id
        seen = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            if self.label(cur) == "METHOD":
                return cur
            cur = self._ast_parent.get(cur)
        return None

    # ------------------------------------------------------------------
    # Methods & call graph
    # ------------------------------------------------------------------

    def method_ids(self) -> List[int]:
        return [_unwrap(v.get("id")) for v in self.vertices if v.get("label") == "METHOD"]

    def internal_methods(self) -> List[int]:
        """User-defined methods (have a body, not operators/stubs)."""
        out = []
        for mid in self.method_ids():
            nm = self.name(mid)
            if nm.startswith("<operator>") or nm.startswith("<global>"):
                continue
            if self.scalar(mid, "IS_EXTERNAL") is True:
                continue
            out.append(mid)
        return out

    def method_filename(self, method_id: Optional[int]) -> str:
        if method_id is None:
            return ""
        return self._filename_by_method.get(method_id, "")

    def call_target(self, call_id: int) -> Optional[int]:
        """Callee METHOD for a call-site (via the CG ``CALL`` edge)."""
        targets = self.out_ids(call_id, "CALL")
        return targets[0] if targets else None

    def call_args(self, call_id: int) -> List[Tuple[int, int]]:
        """``(argument_index, arg_node_id)`` pairs, sorted by index (1-based)."""
        out: List[Tuple[int, int]] = []
        for arg_id in self.out_ids(call_id, "ARGUMENT"):
            idx = self.scalar(arg_id, "ARGUMENT_INDEX")
            out.append((idx if isinstance(idx, int) else 999, arg_id))
        return sorted(out, key=lambda x: x[0])

    def calls_in_method(self, method_id: int) -> List[int]:
        return [d for d in self.ast_descendants(method_id) if self.label(d) == "CALL"]

    def literals_in_method(self, method_id: int) -> List[int]:
        return [d for d in self.ast_descendants(method_id) if self.label(d) == "LITERAL"]

    def params_of_method(self, method_id: int) -> Dict[int, int]:
        """``{index: param_node_id}`` for METHOD_PARAMETER_IN children (1-based)."""
        out: Dict[int, int] = {}
        for child in self.ast_children(method_id):
            if self.label(child) == "METHOD_PARAMETER_IN":
                idx = self.scalar(child, "INDEX")
                if isinstance(idx, int):
                    out[idx] = child
        return out

    def argument_of(self, node_id: int) -> List[Tuple[int, int]]:
        """Calls for which ``node_id`` is a direct argument → ``(call_id, index)``."""
        out: List[Tuple[int, int]] = []
        for call_id, _e in self._in["ARGUMENT"].get(node_id, []):
            if self.label(call_id) != "CALL":
                continue
            idx = self.scalar(node_id, "ARGUMENT_INDEX")
            out.append((call_id, idx if isinstance(idx, int) else 999))
        return out

    # ------------------------------------------------------------------
    # DFG view (REACHING_DEF, def → use, intraprocedural)
    # ------------------------------------------------------------------

    def reaching_out(self, node_id: int) -> List[int]:
        return self.out_ids(node_id, "REACHING_DEF")

    def ref_decl(self, ident_id: int) -> Optional[int]:
        """Declaration (LOCAL / METHOD_PARAMETER_IN) an identifier refers to."""
        decls = self.out_ids(ident_id, "REF")
        return decls[0] if decls else None

    # ------------------------------------------------------------------
    # CFG / dominance view
    # ------------------------------------------------------------------

    def control_structures_in(self, method_id: int) -> List[int]:
        return [d for d in self.ast_descendants(method_id) if self.label(d) == "CONTROL_STRUCTURE"]

    def condition_of(self, control_structure_id: int) -> Optional[int]:
        conds = self.out_ids(control_structure_id, "CONDITION")
        return conds[0] if conds else None

    def dominates(self, dominator_id: int, target_id: int) -> bool:
        """True if ``dominator_id`` dominates ``target_id`` (DOMINATE reachability)."""
        if dominator_id == target_id:
            return True
        stack = [dominator_id]
        seen = set()
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            for nxt in self.out_ids(cur, "DOMINATE"):
                if nxt == target_id:
                    return True
                stack.append(nxt)
        return False
