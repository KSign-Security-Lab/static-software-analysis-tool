from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple, cast

FIELD_ACCESS_OPS = frozenset({"<operator>.indirectFieldAccess", "<operator>.fieldAccess"})
ASSIGNMENT_OPS = frozenset({"<operator>.assignment"})


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict) and "@value" in value:
        return _unwrap(value["@value"])
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def cpg_id(vertex: Dict[str, Any]) -> int:
    return cast(int, _unwrap(vertex.get("id")))


class CPGModel:
    def __init__(self, cpg_json: Any):
        vertices, edges = self._extract_graph(cpg_json)
        self.vertices: List[Dict[str, Any]] = vertices
        self.edges: List[Dict[str, Any]] = edges

        self.by_id: Dict[int, Dict[str, Any]] = {}
        for v in vertices:
            vid = _unwrap(v.get("id"))
            if isinstance(vid, int):
                self.by_id[vid] = v

        self._out: Dict[str, Dict[int, List[Tuple[int, Dict[str, Any]]]]] = defaultdict(lambda: defaultdict(list))
        self._in: Dict[str, Dict[int, List[Tuple[int, Dict[str, Any]]]]] = defaultdict(lambda: defaultdict(list))
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

    @staticmethod
    def _extract_graph(cpg_json: Any) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
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

    def scalar(self, node_id: Optional[int], key: str) -> Optional[Any]:
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

    def out_ids(self, node_id: int, label: str) -> List[int]:
        return [nid for nid, _ in self._out[label].get(node_id, [])]

    def in_ids(self, node_id: int, label: str) -> List[int]:
        return [nid for nid, _ in self._in[label].get(node_id, [])]

    def out_edges(self, node_id: int, label: str) -> List[Tuple[int, Dict[str, Any]]]:
        return list(self._out[label].get(node_id, []))

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
        for parent in self.in_ids(node_id, "AST"):
            return parent
        return None

    def is_internal_call(self, call_id: int) -> bool:
        callee = self.call_target(call_id)
        if callee is None:
            return False
        name = self.name(callee)
        if name.startswith("<operator>") or name.startswith("<global>"):
            return False
        return self.scalar(callee, "IS_EXTERNAL") is not True

    def method_of(self, node_id: Optional[int]) -> Optional[int]:
        cur: Optional[int] = node_id
        seen = set()
        while cur is not None and cur not in seen:
            seen.add(cur)
            if self.label(cur) == "METHOD":
                return cur
            cur = self._ast_parent.get(cur)
        return None

    def method_ids(self) -> List[int]:
        return [_unwrap(v.get("id")) for v in self.vertices if v.get("label") == "METHOD"]

    def internal_methods(self) -> List[int]:
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
        targets = self.out_ids(call_id, "CALL")
        return targets[0] if targets else None

    def call_args(self, call_id: int) -> List[Tuple[int, int]]:
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
        out: Dict[int, int] = {}
        for child in self.ast_children(method_id):
            if self.label(child) == "METHOD_PARAMETER_IN":
                idx = self.scalar(child, "INDEX")
                if isinstance(idx, int):
                    out[idx] = child
        return out

    def argument_of(self, node_id: int) -> List[Tuple[int, int]]:
        out: List[Tuple[int, int]] = []
        for call_id, _e in self._in["ARGUMENT"].get(node_id, []):
            if self.label(call_id) != "CALL":
                continue
            idx = self.scalar(node_id, "ARGUMENT_INDEX")
            out.append((call_id, idx if isinstance(idx, int) else 999))
        return out

    def reaching_out(self, node_id: int) -> List[int]:
        return self.out_ids(node_id, "REACHING_DEF")

    def ref_decl(self, ident_id: int) -> Optional[int]:
        decls = self.out_ids(ident_id, "REF")
        return decls[0] if decls else None

    def control_structures_in(self, method_id: int) -> List[int]:
        return [d for d in self.ast_descendants(method_id) if self.label(d) == "CONTROL_STRUCTURE"]

    def condition_of(self, control_structure_id: int) -> Optional[int]:
        conds = self.out_ids(control_structure_id, "CONDITION")
        return conds[0] if conds else None

    def dominates(self, dominator_id: int, target_id: int) -> bool:
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
