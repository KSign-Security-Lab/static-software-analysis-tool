"""CPG Filter for filtering AST and DFG edges."""

from typing import Dict, List, Literal

from ..types.cpg import EdgeGeneric, NodeInfo, VertexGeneric

EdgeLabel = Literal[
    "ALIAS_OF", "ARGUMENT", "AST", "BINDS", "CALL", "CDG", "CFG",
    "CONDITION", "CONTAINS", "DOMINATE", "EVAL_TYPE", "IMPORTS",
    "PARAMETER_LINK", "POST_DOMINATE", "REACHING_DEF", "REF", "SOURCE_FILE"
]


class CPGFilter:
    """Filter for CPG graph data."""

    def __init__(self, cpg: Dict[str, any]):
        """Initialize filter with CPG data."""
        self.cpg = cpg.get("@value", {}) if isinstance(cpg, dict) else cpg

    def filter_ast(self) -> Dict[str, List]:
        """Filter AST edges and vertices."""
        ast_edges = self._filter_edges_by_label(["AST"])
        ast_vertices = self._filter_vertex_by_edges(ast_edges)
        ast_vertices_with_properties = [
            self._decorate_vertex_with_properties(vertex) for vertex in ast_vertices
        ]

        return {
            "edges": ast_edges,
            "vertices": ast_vertices_with_properties,
        }

    def filter_dfg(self) -> Dict[str, List]:
        """Filter DFG edges and vertices."""
        dfg_edges = self._filter_edges_by_label(["CFG", "CDG"])
        dfg_vertices = self._filter_vertex_by_edges(dfg_edges)
        dfg_vertices_with_properties = [
            self._decorate_vertex_with_properties(vertex) for vertex in dfg_vertices
        ]

        return {
            "edges": dfg_edges,
            "vertices": dfg_vertices_with_properties,
        }

    def _filter_edges_by_label(self, labels: List[str]) -> List[EdgeGeneric]:
        """Filter edges by label."""
        edges = self.cpg.get("edges", [])
        return [edge for edge in edges if edge.get("label") in labels]

    def _filter_vertex_by_edges(self, edges: List[EdgeGeneric]) -> List[VertexGeneric]:
        """Filter vertices by edges."""
        out_ids = {self._unwrap_value(edge.get("outV", {})) for edge in edges}
        in_ids = {self._unwrap_value(edge.get("inV", {})) for edge in edges}
        vertices = self.cpg.get("vertices", [])
        return [
            v for v in vertices
            if self._unwrap_value(v.get("id", {})) in out_ids
            or self._unwrap_value(v.get("id", {})) in in_ids
        ]

    def _decorate_vertex_with_properties(self, node: VertexGeneric) -> NodeInfo:
        """Decorate vertex with properties."""
        id_val = str(self._unwrap_value(node.get("id", {})))
        label_val = node.get("label", "")

        name_val = ""
        raw_name = self._get_prop(node, "NAME")
        unwrapped_name = self._unwrap_value(raw_name)
        if unwrapped_name is not None:
            name_val = str(unwrapped_name)

        code_val = ""
        raw_code = self._get_prop(node, "CODE")
        unwrapped_code = self._unwrap_value(raw_code)
        if unwrapped_code is not None:
            code_val = str(unwrapped_code)

        line_no_val: int | str = ""
        raw_line = self._get_prop(node, "LINE_NUMBER")
        unwrapped_line = self._unwrap_value(raw_line)
        if unwrapped_line is not None:
            line_no_val = unwrapped_line

        return {
            "id": id_val,
            "label": label_val,
            "name": name_val,
            "code": code_val,
            "line_no": line_no_val,
            "properties": node.get("properties", {}),
        }

    def _get_prop(self, node: VertexGeneric, key: str):
        """Get property from node."""
        props = node.get("properties", {})
        return props.get(key)

    def _unwrap_value(self, x: any) -> any:
        """Unwrap GraphSON or VertexProperty value."""
        if x is None:
            return None
        if isinstance(x, (str, int, float, bool)):
            return x
        if isinstance(x, dict):
            if "@value" in x:
                inner = x["@value"]
                if isinstance(inner, dict) and "@value" in inner:
                    return inner["@value"]
                return inner
        return None


