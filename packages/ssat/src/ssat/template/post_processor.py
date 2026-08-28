"""Post-processor for template nodes."""

from typing import Any, Dict, List, Optional, cast

from ..types.cpg import CPGRoot
from ..types.node import TemplateNodes
from ..types.template.BaseNode.base_types import TemplateNodeTypes


def as_template_node(data: Dict[str, Any]) -> TemplateNodes:
    """Tag a dynamically built dict as a template node.

    TemplateNodes is a union of TypedDicts, so a dict assembled at runtime (by
    spreading an existing node and overriding keys) never matches structurally.
    One cast in one place beats a `# type: ignore` at every construction site.
    """
    return cast(TemplateNodes, data)


class PostProcessor:
    """Post-processor for template nodes."""

    def add_code_properties(self, nodes: List[TemplateNodes], cpg: CPGRoot) -> List[TemplateNodes]:
        """Add code properties to all AST nodes and its children."""
        result: List[TemplateNodes] = []
        for node in nodes:
            node_id = node.get("id") if isinstance(node, dict) else getattr(node, "id", None)
            vertices = cpg.get("export", {}).get("@value", {}).get("vertices", [])
            vertex = next((v for v in vertices if self._unwrap_value(v.get("id", {})) == node_id), None)

            code: Optional[str] = None
            if vertex:
                props = vertex.get("properties", {})
                code_prop = props.get("CODE")
                if isinstance(code_prop, dict):
                    inner = code_prop.get("@value", {})
                    if isinstance(inner, dict):
                        arr = inner.get("@value", [])
                        if isinstance(arr, list):
                            code = "".join(str(x) for x in arr)

            children = node.get("children", []) if isinstance(node, dict) else getattr(node, "children", [])
            processed_node = {
                **(node if isinstance(node, dict) else node.__dict__),
                "code": code,
                "children": self.add_code_properties(children, cpg) if children else [],
            }
            result.append(as_template_node(processed_node))

        return result

    def isolate_translation_unit(self, nodes: List[TemplateNodes]) -> List[TemplateNodes]:
        """Isolate the TranslationUnit node from the AST."""
        tu = [node for node in nodes if self._get_node_type(node) == TemplateNodeTypes.TranslationUnit]
        if len(tu) == 0:
            raise ValueError("No TranslationUnit node found in the provided AST")
        return tu

    def merge_array_size_allocation(self, nodes: List[TemplateNodes]) -> List[TemplateNodes]:
        """Merge ArraySizeAllocation into ArrayDeclaration if applicable."""
        result: List[TemplateNodes] = []
        for node in nodes:
            children = node.get("children", []) if isinstance(node, dict) else getattr(node, "children", [])
            if not children:
                result.append(node)
                continue

            merged_children: List[TemplateNodes] = []
            i = 0
            while i < len(children):
                current = children[i]
                next_node = children[i + 1] if i + 1 < len(children) else None

                current_type = self._get_node_type(current)
                next_type = self._get_node_type(next_node) if next_node else None

                if (
                    next_node is not None
                    and current_type == TemplateNodeTypes.ArrayDeclaration
                    and next_type == TemplateNodeTypes.ArraySizeAllocation
                ):
                    array_decl = current
                    array_size = next_node

                    merged_children.append(
                        as_template_node(
                            {
                                **(array_decl if isinstance(array_decl, dict) else array_decl.__dict__),
                                "length": array_decl.get("length")
                                if array_decl.get("length") == array_size.get("length")
                                else array_size.get("length"),
                                "children": (array_decl.get("children", []) or [])
                                + (array_size.get("children", []) or []),
                            }
                        )
                    )

                    i += 2  # skip next (ArraySizeAllocation)
                else:
                    current_children = (
                        current.get("children", []) if isinstance(current, dict) else getattr(current, "children", [])
                    )
                    merged_children.append(
                        as_template_node(
                            {
                                **(current if isinstance(current, dict) else current.__dict__),
                                "children": self.merge_array_size_allocation(current_children)
                                if current_children
                                else current_children,
                            }
                        )
                    )
                    i += 1

            result.append(
                as_template_node(
                    {
                        **(node if isinstance(node, dict) else node.__dict__),
                        "children": merged_children,
                    }
                )
            )

        return result

    def remove_invalid_nodes(self, nodes: List[TemplateNodes]) -> List[TemplateNodes]:
        """Walk the AST and remove any nodes with a missing or invalid nodeType."""
        result: List[TemplateNodes] = []
        for node in nodes:
            result.extend(self._validate_node(node))
        return result

    def _get_node_type(self, node: Any) -> Optional[TemplateNodeTypes]:
        """Get node type from node."""
        if isinstance(node, dict):
            return node.get("nodeType")
        return getattr(node, "nodeType", None)

    def _validate_node(self, node: TemplateNodes) -> List[TemplateNodes]:
        """Validate node and return list of valid nodes."""
        node_dict = node if isinstance(node, dict) else node.__dict__
        if "nodeType" not in node_dict:
            # Inline grandchildren
            children = node_dict.get("children", [])
            result: List[TemplateNodes] = []
            for child in children:
                result.extend(self._validate_node(child))
            return result

        # Otherwise, keep this node but recurse into its children
        children = node_dict.get("children") or []
        processed_children: List[TemplateNodes] = []
        for child in children:
            processed_children.extend(self._validate_node(child))

        return [
            as_template_node(
                {
                    **node_dict,
                    "children": processed_children,
                }
            )
        ]

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
