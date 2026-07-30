"""Template extractor for building tree structures from CPG data."""

from typing import Any, Dict, List, Optional, Union

from ..types.cpg import NodeInfo, TreeNode


class TemplateExtractor:
    """Extracts template tree structures from CPG data."""

    def get_template_tree(self, cpg: Any) -> List[TreeNode]:
        """Extract template tree from CPG data."""
        if not isinstance(cpg, dict) or cpg is None or "@value" not in cpg:
            return []

        data: Dict[str, Any] = cpg
        inner = data.get("@value")
        if (
            not isinstance(inner, dict)
            or not isinstance(inner.get("edges"), list)
            or not isinstance(inner.get("vertices"), list)
        ):
            return []

        edges = inner["edges"]
        nodes = inner["vertices"]

        ast_edges = [e for e in edges if e.get("label") == "AST"]

        # Build node dictionary
        node_dict: Dict[str, NodeInfo] = {}
        for n in nodes:
            if self._is_value_wrapper(n.get("id")):
                id_val = n["id"].get("@value")
                if isinstance(id_val, (str, int)):
                    key = str(id_val)
                    node_dict[key] = n

        # Build AST edge data
        ast_data: List[Dict[str, Any]] = []
        for edge in ast_edges:
            out_node: Optional[NodeInfo] = None
            in_node: Optional[NodeInfo] = None

            if self._is_value_wrapper(edge.get("outV")):
                out_id_raw = edge["outV"].get("@value")
                out_id_unwrapped = self._unwrap_value(out_id_raw)
                out_id_str = str(out_id_unwrapped) if out_id_unwrapped is not None else ""
                out_node = node_dict.get(out_id_str)

            if self._is_value_wrapper(edge.get("inV")):
                in_id_raw = edge["inV"].get("@value")
                in_id_unwrapped = self._unwrap_value(in_id_raw)
                in_id_str = str(in_id_unwrapped) if in_id_unwrapped is not None else ""
                in_node = node_dict.get(in_id_str)

            ast_data.append(
                {
                    "edge": edge,
                    "inV_node": in_node,
                    "outV_node": out_node,
                }
            )

        # Build node info map and children map
        node_info_map: Dict[str, NodeInfo] = {}
        children_map: Dict[str, List[str]] = {}

        for item in ast_data:
            edge = item["edge"]

            if self._is_value_wrapper(edge.get("outV")) and self._is_value_wrapper(edge.get("inV")):
                out_id = str(self._unwrap_value(edge["outV"].get("@value")))
                in_id_val = edge["inV"].get("@value")
                if isinstance(in_id_val, (str, int)):
                    in_id = str(in_id_val)
                else:
                    in_id_unwrapped = self._unwrap_value(in_id_val)
                    in_id = str(in_id_unwrapped) if in_id_unwrapped is not None else ""

                if out_id not in node_info_map:
                    node_info_map[out_id] = self._extract_node_info(item["outV_node"])
                if in_id not in node_info_map:
                    node_info_map[in_id] = self._extract_node_info(item["inV_node"])

                if out_id not in children_map:
                    children_map[out_id] = []
                children_map[out_id].append(in_id)

        # Find root nodes
        all_ids = set(node_info_map.keys())
        child_ids = set()
        for child_arr in children_map.values():
            for cid in child_arr:
                child_ids.add(cid)
        root_ids = [rid for rid in all_ids if rid not in child_ids]

        def build_tree(node_id: str) -> TreeNode:
            """Build tree recursively."""
            info = node_info_map[node_id]

            node: TreeNode = {
                "id": info.get("id", ""),
                "label": info.get("label", ""),
                "name": info.get("name", ""),
                "code": info.get("code", ""),
                "line_no": info.get("line_no", ""),
                "properties": info.get("properties", {}),
                "children": [],
            }

            child_ids_list = children_map.get(node_id, [])
            for cid in child_ids_list:
                node["children"].append(build_tree(cid))

            return node

        return [build_tree(rid) for rid in root_ids]

    def _extract_node_info(self, node: Optional[Dict[str, Any]]) -> NodeInfo:
        """Flatten a raw GraphSON vertex into a NodeInfo.

        The parameter is the vertex as joern-export writes it (ids and property
        values wrapped in ``{"@type": ..., "@value": ...}``), not a NodeInfo --
        producing one is this method's job. It was annotated as ``NodeInfo``,
        which made every unwrapping step below a type error.
        """
        if node is None:
            raise ValueError("Node cannot be None in extractNodeInfo")

        id_val = ""
        if self._is_value_wrapper(node.get("id")):
            id_raw = node["id"].get("@value")
            if isinstance(id_raw, (str, int)):
                id_val = str(id_raw)

        label_val = node.get("label", "")

        name_val = ""
        if "NAME" in node.get("properties", {}):
            raw_name = node["properties"]["NAME"]
            unwrapped_name = self._unwrap_value(raw_name)
            if unwrapped_name is not None:
                name_val = str(unwrapped_name)

        code_val = ""
        if "CODE" in node.get("properties", {}):
            raw_code = node["properties"]["CODE"]
            unwrapped_code = self._unwrap_value(raw_code)
            if unwrapped_code is not None:
                code_val = str(unwrapped_code)

        line_no_val: Union[int, str] = ""
        if "LINE_NUMBER" in node.get("properties", {}):
            raw_line = node["properties"]["LINE_NUMBER"]
            unwrapped_line = self._unwrap_value(raw_line)
            if unwrapped_line is not None:
                line_no_val = unwrapped_line

        return {
            "code": code_val,
            "id": id_val,
            "label": label_val,
            "line_no": line_no_val,
            "name": name_val,
            "properties": node.get("properties", {}),
        }

    def _is_value_wrapper(self, x: Any) -> bool:
        """Check if x is an object with a '@value' key."""
        return isinstance(x, dict) and x is not None and "@value" in x

    def _unwrap_value(self, x: Any) -> Optional[Union[int, str]]:
        """Unwrap GraphSON value wrapper."""
        if x is None:
            return None

        if isinstance(x, (str, int, float)):
            return x if isinstance(x, (str, int)) else int(x)

        if self._is_value_wrapper(x):
            inner = x.get("@value")

            if isinstance(inner, (str, int, float)):
                return inner if isinstance(inner, (str, int)) else int(inner)

            if self._is_value_wrapper(inner):
                return self._unwrap_value(inner.get("@value"))

            if isinstance(inner, list):
                return self._unwrap_value(inner)

            return None

        if isinstance(x, list):
            for elem in x:
                unwrapped = self._unwrap_value(elem)
                if unwrapped is not None:
                    return unwrapped
            return None

        return None
