"""Template converter for transforming CPG trees to template nodes."""

import logging
import re
from typing import Any, List, NoReturn, Optional, Union, cast

from ..types.cpg import TreeNode
from ..types.template import (
    IAddressOfExpression,
    IArrayDeclaration,
    IArraySizeAllocation,
    IArraySubscriptExpression,
    IAssignmentExpression,
    IBinaryExpression,
    IBreakStatement,
    ICaseLabel,
    ICastExpression,
    ICompoundStatement,
    IContinueStatement,
    IDefaultLabel,
    IDoWhileStatement,
    IForStatement,
    IFunctionDeclaration,
    IFunctionDefinition,
    IGotoStatement,
    IIdentifier,
    IIfStatement,
    IIncludeDirective,
    ILabel,
    ILiteral,
    IMemberAccess,
    IParameterDeclaration,
    IParameterList,
    IPointerDeclaration,
    IPointerDereference,
    IReturnStatement,
    ISizeOfExpression,
    IStandardLibCall,
    IStructType,
    ISwitchStatement,
    ITranslationUnit,
    ITypeDefinition,
    IUnaryExpression,
    IUnionType,
    IUserDefinedCall,
    IVariableDeclaration,
    IWhileStatement,
)
from ..types.template.BaseNode.base_types import TemplateNodeTypes
from ..knowledge.library_calls import STANDARD_LIB_CALLS
from ..utils.random import random_int_with_length
from .config.binary_expression import BinaryExpressionOperatorMap
from .config.predefined import IdentifierToLiteralMap, PredefinedIdentifierTypes
from .config.unary_expression import UnaryExpressionOperatorMap
from .type_wrapper import binary_unary_type_wrapper

logger = logging.getLogger(__name__)


def _passthrough_node(node: TreeNode, children: List[TemplateNodes]) -> TemplateNodes:
    """Fallback conversion: keep the raw CPG node, convert its children.

    The result is deliberately *not* a well-formed template node -- it carries
    the CPG's own keys (``label``, ``line_no``, ``properties``) and no
    ``nodeType``. That is the contract: ``PostProcessor.remove_invalid_nodes``
    drops anything without a valid ``nodeType`` in a later pass. Hence the cast.
    """
    return cast(TemplateNodes, {**node, "children": children})


# Type aliases
TemplateNodes = Union[
    IAddressOfExpression,
    IArrayDeclaration,
    IArraySizeAllocation,
    IArraySubscriptExpression,
    IAssignmentExpression,
    IBinaryExpression,
    IBreakStatement,
    ICaseLabel,
    ICastExpression,
    ICompoundStatement,
    IContinueStatement,
    IDefaultLabel,
    IDoWhileStatement,
    IForStatement,
    IFunctionDeclaration,
    IFunctionDefinition,
    IGotoStatement,
    IIdentifier,
    IIfStatement,
    IIncludeDirective,
    ILabel,
    ILiteral,
    IMemberAccess,
    IParameterDeclaration,
    IParameterList,
    IPointerDeclaration,
    IPointerDereference,
    IReturnStatement,
    ISizeOfExpression,
    IStandardLibCall,
    IStructType,
    ISwitchStatement,
    ITranslationUnit,
    ITypeDefinition,
    IUnaryExpression,
    IUnionType,
    IUserDefinedCall,
    IVariableDeclaration,
    IWhileStatement,
]

CallReturnTypes = Union[
    IAddressOfExpression,
    IArraySizeAllocation,
    IArraySubscriptExpression,
    IAssignmentExpression,
    IBinaryExpression,
    ICastExpression,
    ILiteral,
    IMemberAccess,
    ISizeOfExpression,
    IStandardLibCall,
    IUnaryExpression,
    IUserDefinedCall,
    None,
]


class TemplateConverter:
    """Converts CPG trees to template nodes."""

    def __init__(self) -> None:
        """Initialize converter."""
        self.call_collection: List[str] = []

    def convert_tree(self, nodes: List[TreeNode]) -> List[TemplateNodes]:
        """Convert an array of root nodes into TemplateNodes[], skipping undefined conversions."""
        converted_nodes: List[TemplateNodes] = []
        for node in nodes:
            single = self._dispatch_convert(node)
            if single is not None:
                converted_nodes.append(single)
        return converted_nodes

    def get_call_collection(self) -> List[str]:
        """Get collected call names."""
        return self.call_collection

    def _assert_never(self, x: Any) -> NoReturn:
        """Every CPG label must be handled explicitly."""
        raise ValueError(f"Unexpected label: {x}")

    def _converted_children(self, children: List[TreeNode]) -> List[TemplateNodes]:
        """Convert children nodes."""
        return [child for child in [self._dispatch_convert(child) for child in children] if child is not None]

    def _dispatch_convert(self, node: TreeNode) -> Optional[TemplateNodes]:
        """Dispatch helper: switch on node.label, extract payload, call the correct handler."""
        try:
            label = node.get("label", "")
            if label in [
                "BINDING",
                "DEPENDENCY",
                "META_DATA",
                "METHOD_PARAMETER_OUT",
                "METHOD_RETURN",
                "MODIFIER",
                "NAMESPACE",
                "NAMESPACE_BLOCK",
                "TYPE",
                "TYPE_REF",
                "UNKNOWN",
            ]:
                return self._handle_skipped_nodes(node)
            elif label == "BLOCK":
                return self._handle_block(node)
            elif label == "CALL":
                return self._handle_call(node)
            elif label == "CONTROL_STRUCTURE":
                return self._handle_control_structure(node)
            elif label == "FIELD_IDENTIFIER":
                return self._handle_field_identifier(node)
            elif label == "FILE":
                return self._handle_file(node)
            elif label == "IDENTIFIER":
                return self._handle_identifier(node)
            elif label == "IMPORT":
                return self._handle_import(node)
            elif label == "JUMP_TARGET":
                return self._handle_jump_target(node)
            elif label == "LITERAL":
                return self._handle_literal(node)
            elif label == "LOCAL":
                return self._handle_local(node)
            elif label == "MEMBER":
                return self._handle_member(node)
            elif label == "METHOD":
                return self._handle_method(node)
            elif label == "METHOD_PARAMETER_IN":
                return self._handle_method_param_in(node)
            elif label == "METHOD_REF":
                return self._handle_method_ref(node)
            elif label == "RETURN":
                return self._handle_return(node)
            elif label == "TYPE_DECL":
                return self._handle_type_decl(node)
            else:
                return self._assert_never(label)
        except Exception as error:
            error_msg = str(error)
            # The raised ValueError already carries id/label/name, and each
            # recursion level re-wraps it -- printing here as well produced one
            # full stanza per ancestor node for a single root cause.
            logger.debug(
                "conversion failed at node id=%s label=%s name=%s: %s",
                node.get("id", ""),
                node.get("label", ""),
                node.get("name", ""),
                error_msg,
            )
            raise ValueError(
                f"Conversion failed for node id={node.get('id')} label={node.get('label')} name={node.get('name')}: {error_msg}"
            ) from error

    def _format_string(self, s: str) -> str:
        """Format the string to remove quotes and escape characters."""
        return s.replace('"', "").replace("\\n", "\n").replace("\\t", "\t")

    def _handle_block(self, node: TreeNode) -> Optional[ICompoundStatement]:
        """Handle BLOCK node."""
        node_id = node.get("id", "")
        return {
            "nodeType": TemplateNodeTypes.CompoundStatement,
            "id": int(node_id) if isinstance(node_id, (str, int)) and str(node_id).isdigit() else -999,
            "children": self._converted_children(node.get("children", [])),
        }

    def _handle_call(self, node: TreeNode) -> Optional[CallReturnTypes]:
        """Handle CALL node."""
        node_name = node.get("name", "")
        if node_name not in self.call_collection:
            self.call_collection.append(node_name)

        if node_name.startswith("<operator>."):
            return self._handle_call_operators(node)

        param_list_wrapper: IParameterList = {
            "nodeType": TemplateNodeTypes.ParameterList,
            "id": random_int_with_length(len(str(node.get("id", ""))) + 3) if node.get("id") else -999,
            "children": self._converted_children(node.get("children", [])),
        }

        is_standard_lib = node_name in STANDARD_LIB_CALLS
        return {
            "nodeType": TemplateNodeTypes.StandardLibCall if is_standard_lib else TemplateNodeTypes.UserDefinedCall,
            "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
            "name": node_name,
            "children": [param_list_wrapper],
        }

    def _handle_call_operators(self, node: TreeNode) -> Optional[CallReturnTypes]:
        """Handle call operators."""
        node_name = node.get("name", "")
        properties = node.get("properties", {})

        if node_name in BinaryExpressionOperatorMap:
            return {
                "nodeType": TemplateNodeTypes.BinaryExpression,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "operator": BinaryExpressionOperatorMap[node_name],
                "type": binary_unary_type_wrapper(node),
                "children": self._converted_children(node.get("children", [])),
            }

        if node_name in UnaryExpressionOperatorMap:
            return {
                "nodeType": TemplateNodeTypes.UnaryExpression,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "operator": UnaryExpressionOperatorMap[node_name],
                "type": binary_unary_type_wrapper(node),
                "children": self._converted_children(node.get("children", [])),
            }

        if node_name == "<operator>.addressOf":
            identifier_child = next(
                (
                    child
                    for child in node.get("children", [])
                    if child.get("label") == "IDENTIFIER" and child.get("name") == node.get("code", "").replace("&", "")
                ),
                None,
            )
            type_val = "<unknown>"
            if identifier_child:
                id_props = identifier_child.get("properties", {})
                type_full_name = id_props.get("TYPE_FULL_NAME", {})
                if isinstance(type_full_name, dict):
                    inner = type_full_name.get("@value", {})
                    if isinstance(inner, dict):
                        arr = inner.get("@value", [])
                        if isinstance(arr, list):
                            type_val = "/".join(str(x) for x in arr) + "*"
            return {
                "nodeType": TemplateNodeTypes.AddressOfExpression,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "type": type_val,
                "children": self._converted_children(node.get("children", [])),
            }

        if node_name == "<operator>.assignment":
            children = node.get("children", [])
            if len(children) != 2:
                raise ValueError(f"Call node {node.get('id')} has {len(children)} children, expected 2.")
            alloc_child = [child for child in children if child.get("name") == "<operator>.alloc"]

            if len(alloc_child) == 1:
                type_full_name = self._unwrap_graphson_scalar(properties.get("TYPE_FULL_NAME", {}))
                raw_size_match = re.search(r"\[(\d+)\]", str(type_full_name))
                full_raw_type = raw_size_match.group(1) if raw_size_match else None

                length: Union[int, str] = (
                    int(full_raw_type)
                    if full_raw_type and full_raw_type.isdigit()
                    else (full_raw_type if full_raw_type else type_full_name)
                )

                return {
                    "nodeType": TemplateNodeTypes.ArraySizeAllocation,
                    "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                    "length": length,
                    "children": self._converted_children(children),
                }

            return {
                "nodeType": TemplateNodeTypes.AssignmentExpression,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "operator": "=",
                "children": self._converted_children(children),
            }

        if node_name == "<operator>.cast":
            code = node.get("code", "")
            filtered_casting_type = code.split(")")[0].split("(")[1] if "(" in code and ")" in code else code
            return {
                "nodeType": TemplateNodeTypes.CastExpression,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "targetType": filtered_casting_type or code,
                "children": self._converted_children(
                    [child for child in node.get("children", []) if child.get("label") != "TYPE_REF"]
                ),
            }

        if node_name in ["<operator>.fieldAccess", "<operator>.indirectFieldAccess"]:
            type_full_name = self._unwrap_graphson_scalar(properties.get("TYPE_FULL_NAME", {}))
            return {
                "nodeType": TemplateNodeTypes.MemberAccess,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "type": type_full_name,
                "children": self._converted_children(node.get("children", [])),
            }

        if node_name == "<operator>.indirectIndexAccess":
            return {
                "nodeType": TemplateNodeTypes.ArraySubscriptExpression,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(node.get("children", [])),
            }

        if node_name == "<operator>.sizeOf":
            return {
                "nodeType": TemplateNodeTypes.SizeOfExpression,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(node.get("children", [])),
            }

        # Fallback
        return _passthrough_node(node, self._converted_children(node.get("children", [])))

    def _handle_control_structure(
        self, node: TreeNode
    ) -> Optional[
        Union[
            IBreakStatement,
            IDoWhileStatement,
            IForStatement,
            IGotoStatement,
            IIfStatement,
            ISwitchStatement,
            IWhileStatement,
        ]
    ]:
        """Handle CONTROL_STRUCTURE node."""
        properties = node.get("properties", {})
        cs_type = self._unwrap_graphson_scalar(properties.get("CONTROL_STRUCTURE_TYPE", {}))

        if cs_type == "BREAK":
            return {
                "nodeType": TemplateNodeTypes.BreakStatement,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(node.get("children", [])),
            }
        elif cs_type == "DO":
            return {
                "nodeType": TemplateNodeTypes.DoWhileStatement,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(node.get("children", [])),
            }
        elif cs_type == "FOR":
            return {
                "nodeType": TemplateNodeTypes.ForStatement,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(node.get("children", [])),
            }
        elif cs_type == "GOTO":
            code = node.get("code", "")
            jump_target = code.split("goto ")[1].replace(";", "") if "goto " in code else code
            return {
                "nodeType": TemplateNodeTypes.GotoStatement,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "jumpTarget": jump_target,
                "children": self._converted_children(node.get("children", [])),
            }
        elif cs_type == "IF":
            children = node.get("children", [])
            if len(children) < 2:
                raise ValueError(
                    f"Control structure node {node.get('id')} has {len(children)} children, expected at least 2."
                )

            condition_child = self._dispatch_convert(children[0]) if len(children) > 0 else None
            if_true_child = self._dispatch_convert(children[1]) if len(children) > 1 else None
            else_branch = self._dispatch_convert(children[2]) if len(children) > 2 else None
            else_children = else_branch.get("children") or [] if else_branch else []
            else_child = else_children[0] if else_children else None

            restructured_children = []
            if condition_child:
                restructured_children.append(condition_child)
            if if_true_child:
                restructured_children.append(if_true_child)
            if else_child:
                restructured_children.append(else_child)

            return {
                "nodeType": TemplateNodeTypes.IfStatement,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": restructured_children,
            }
        elif cs_type == "SWITCH":
            children = node.get("children", [])
            block_child = next((child for child in children if child.get("label") == "BLOCK"), None)
            block_children = block_child.get("children", []) if block_child else []
            reshaped = self._reshape_label_children(block_children)
            full_children = [child for child in children if child.get("label") != "BLOCK"] + reshaped
            return {
                "nodeType": TemplateNodeTypes.SwitchStatement,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(full_children),
            }
        elif cs_type == "WHILE":
            return {
                "nodeType": TemplateNodeTypes.WhileStatement,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(node.get("children", [])),
            }

        # Fallback
        return _passthrough_node(node, self._converted_children(node.get("children", [])))

    def _handle_field_identifier(self, node: TreeNode) -> Optional[IIdentifier]:
        """Handle FIELD_IDENTIFIER node."""
        return {
            "nodeType": TemplateNodeTypes.Identifier,
            "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
            "name": node.get("name") or node.get("code", ""),
            "size": "<unknown>",
            "type": "<unknown>",
            "children": self._converted_children(node.get("children", [])),
        }

    def _handle_file(self, node: TreeNode) -> Optional[ITranslationUnit]:
        """Handle FILE node."""
        node_name = node.get("name", "")
        if node_name.endswith(".c") or node_name.endswith(".cpp"):
            return {
                "nodeType": TemplateNodeTypes.TranslationUnit,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(node.get("children", [])),
            }
        return None

    def _handle_identifier(self, node: TreeNode) -> Optional[Union[IIdentifier, ILiteral, IPointerDereference]]:
        """Handle IDENTIFIER node."""
        properties = node.get("properties", {})
        type_full_name = self._unwrap_graphson_scalar(properties.get("TYPE_FULL_NAME", {}))
        type_full_name_str = str(type_full_name)

        is_array = "[" in type_full_name_str and "]" in type_full_name_str
        size = type_full_name_str.split("[")[1].split("]")[0] if is_array else "<not-array>"
        type_val = type_full_name_str.split("[")[0] if is_array else type_full_name_str

        node_name = node.get("name", "")
        predefined_type = PredefinedIdentifierTypes.get(node_name)

        if "*" in type_val:
            pointer_type = type_val.replace("*", "").strip()
            return {
                "nodeType": TemplateNodeTypes.PointerDereference,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "type": pointer_type,
                "children": [
                    {
                        "nodeType": TemplateNodeTypes.Identifier,
                        "id": random_int_with_length(len(str(node.get("id", ""))) + 3) if node.get("id") else -999,
                        "name": node_name,
                        "type": predefined_type or type_val,
                        "size": size if is_array else None,
                        "children": self._converted_children(node.get("children", [])),
                    }
                ],
            }

        if node_name in IdentifierToLiteralMap:
            return {
                "nodeType": TemplateNodeTypes.Literal,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "type": predefined_type or type_val,
                "value": node_name,
                "children": self._converted_children(node.get("children", [])),
            }

        base_obj: IIdentifier = {
            "nodeType": TemplateNodeTypes.Identifier,
            "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
            "name": node_name,
            "type": predefined_type or type_val,
            "children": self._converted_children(node.get("children", [])),
        }

        if is_array:
            base_obj["size"] = size
        return base_obj

    def _handle_import(self, node: TreeNode) -> Optional[IIncludeDirective]:
        """Handle IMPORT node."""
        return None  # Drop imports for now
        # properties = node.get("properties", {})
        # imported_as = self._unwrap_graphson_scalar(properties.get("IMPORTED_AS", {}))
        # return {
        #     "nodeType": TemplateNodeTypes.IncludeDirective,
        #     "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
        #     "name": "/".join(str(x) for x in imported_as) if isinstance(imported_as, list) else "",
        #     "children": self._converted_children(node.get("children", [])),
        # }

    def _handle_jump_target(self, node: TreeNode) -> Optional[Union[ICaseLabel, IDefaultLabel, ILabel]]:
        """Handle JUMP_TARGET node."""
        node_name = node.get("name", "")
        if node_name == "case":
            return {
                "nodeType": TemplateNodeTypes.CaseLabel,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(node.get("children", [])),
            }
        if node_name == "default":
            return {
                "nodeType": TemplateNodeTypes.DefaultLabel,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "children": self._converted_children(node.get("children", [])),
            }

        properties = node.get("properties", {})
        label_name = self._unwrap_graphson_scalar(properties.get("NAME", {}))
        return {
            "nodeType": TemplateNodeTypes.Label,
            "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
            "name": str(label_name),
            "children": self._converted_children(node.get("children", [])),
        }

    def _handle_literal(self, node: TreeNode) -> Optional[ILiteral]:
        """Handle LITERAL node."""
        children = node.get("children", [])
        if len(children) != 0:
            raise ValueError(f"Literal node {node.get('id')} has {len(children)} children, expected 0.")

        properties = node.get("properties", {})
        type_full_name = self._unwrap_graphson_scalar(properties.get("TYPE_FULL_NAME", {}))
        type_full_name_str = str(type_full_name)
        is_string = "char" in type_full_name_str

        node_name = node.get("name", "")
        predefined_type = PredefinedIdentifierTypes.get(node_name)

        base_obj: ILiteral = {
            "nodeType": TemplateNodeTypes.Literal,
            "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
            "type": predefined_type or type_full_name_str,
            "value": self._format_string(node.get("code", "")),
        }

        if is_string:
            base_obj["size"] = len(self._format_string(node.get("code", "")))

        return base_obj

    def _handle_local(self, node: TreeNode) -> Union[IArrayDeclaration, IPointerDeclaration, IVariableDeclaration]:
        """Handle LOCAL node."""
        properties = node.get("properties", {})
        node_name = node.get("name", "")
        predefined_type = PredefinedIdentifierTypes.get(node_name)

        type_full_name = self._unwrap_graphson_scalar(properties.get("TYPE_FULL_NAME", {}))
        type_full_name_str = str(type_full_name)

        code = node.get("code", "")
        storage = None
        if type_full_name_str and type_full_name_str in code and code.strip().startswith(type_full_name_str):
            storage = None
        elif type_full_name_str:
            parts = code.split(type_full_name_str)
            storage = parts[0].strip() if len(parts) > 1 else None

        if type_full_name and len(type_full_name) > 0:
            type_full_name_str = str(type_full_name)

            if "[" in type_full_name_str and "]" in type_full_name_str:
                element_type = type_full_name_str.split("[")[0]
                full_raw_type = type_full_name_str.split("[")[1].split("]")[0]
                length = int(full_raw_type) if full_raw_type.isdigit() else full_raw_type

                return {
                    "nodeType": TemplateNodeTypes.ArrayDeclaration,
                    "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                    "name": node_name,
                    "elementType": element_type,
                    "length": length,
                    "storage": storage,
                    "children": self._converted_children(node.get("children", [])),
                }

            if "*" in type_full_name_str:
                level = type_full_name_str.count("*")
                points_to = type_full_name_str.replace("*", "")

                return {
                    "nodeType": TemplateNodeTypes.PointerDeclaration,
                    "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                    "name": node_name,
                    "pointingType": points_to,
                    "level": level,
                    "storage": storage,
                    "children": self._converted_children(node.get("children", [])),
                }

        return {
            "nodeType": TemplateNodeTypes.VariableDeclaration,
            "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
            "name": node_name,
            "type": predefined_type or type_full_name_str,
            "storage": storage,
            "children": self._converted_children(node.get("children", [])),
        }

    def _handle_member(self, node: TreeNode) -> Union[IArrayDeclaration, IPointerDeclaration, IVariableDeclaration]:
        """Handle MEMBER node."""
        return self._handle_local(node)  # Member is handled the same way as Local

    def _handle_method(self, node: TreeNode) -> Optional[Union[IFunctionDeclaration, IFunctionDefinition]]:
        """Handle METHOD node."""
        properties = node.get("properties", {})
        children = node.get("children", [])
        first_block = next((child for child in children if child.get("label") == "BLOCK"), None)

        filename_val = self._unwrap_graphson_scalar(properties.get("FILENAME", {}))
        ast_parent_val = self._unwrap_graphson_scalar(properties.get("AST_PARENT_FULL_NAME", {}))
        is_external_val = self._unwrap_graphson_scalar(properties.get("IS_EXTERNAL", {})) or False
        signature_str = str(self._unwrap_graphson_scalar(properties.get("SIGNATURE", {})))

        if str(filename_val) + ":<global>" == str(ast_parent_val) and not is_external_val and len(signature_str) > 0:
            param_list: IParameterList = {
                "nodeType": TemplateNodeTypes.ParameterList,
                "id": random_int_with_length(len(str(node.get("id", ""))) + 3) if node.get("id") else -999,
                "children": [
                    child
                    for child in [
                        self._dispatch_convert(child)
                        for child in children
                        if child.get("label") == "METHOD_PARAMETER_IN"
                    ]
                    if child is not None
                    and isinstance(child, dict)
                    and child.get("nodeType") == TemplateNodeTypes.ParameterDeclaration
                ],
            }

            if not param_list.get("children"):
                param_list["children"] = [
                    {
                        "nodeType": TemplateNodeTypes.ParameterDeclaration,
                        "id": random_int_with_length(len(str(node.get("id", ""))) + 3) if node.get("id") else -999,
                        "name": "<empty>",
                        "type": "<empty>",
                        "children": [],
                    }
                ]

            non_func_param_children = [
                child
                for child in [
                    self._dispatch_convert(child)
                    for child in children
                    if child.get("label") != "METHOD_PARAMETER_IN"
                    and child.get("label") not in ["METHOD_RETURN", "MODIFIER"]
                    and not (child.get("label") == "BLOCK" and len(child.get("children", [])) == 0)
                ]
                if child is not None
            ]

            return {
                "nodeType": TemplateNodeTypes.FunctionDeclaration
                if (first_block and first_block.get("code") == "<empty>")
                else TemplateNodeTypes.FunctionDefinition,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "name": node.get("name", ""),
                "returnType": signature_str.split("(")[0] if "(" in signature_str else signature_str,
                "children": [param_list] + non_func_param_children,
            }

        # Fallback
        return _passthrough_node(node, self._converted_children(children))

    def _handle_method_param_in(self, node: TreeNode) -> Optional[IParameterDeclaration]:
        """Handle METHOD_PARAMETER_IN node."""
        properties = node.get("properties", {})
        type_full_name = self._unwrap_graphson_scalar(properties.get("TYPE_FULL_NAME", {}))
        if not type_full_name:
            raise ValueError(f"Method parameter in node {node.get('id')} has no type.")

        type_full_name_str = str(type_full_name)
        is_array = "[" in type_full_name_str and "]" in type_full_name_str
        size = type_full_name_str.split("[")[1].split("]")[0] if is_array else None
        type_val = type_full_name_str.split("[")[0] if is_array else type_full_name_str

        return {
            "nodeType": TemplateNodeTypes.ParameterDeclaration,
            "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
            "name": node.get("name", ""),
            "type": type_val,
            "size": size,
            "children": self._converted_children(node.get("children", [])),
        }

    def _handle_method_ref(self, node: TreeNode) -> Optional[IIdentifier]:
        """Handle METHOD_REF node."""
        properties = node.get("properties", {})
        method_full_name = self._unwrap_graphson_scalar(properties.get("METHOD_FULL_NAME", {}))
        type_full_name = self._unwrap_graphson_scalar(properties.get("TYPE_FULL_NAME", {}))

        if not type_full_name:
            raise ValueError(f"Method reference node {node.get('id')} has no type.")

        name = str(method_full_name) if method_full_name else (node.get("name") or "<unknown>")
        type_full_name_str = str(type_full_name)
        is_array = "[" in type_full_name_str and "]" in type_full_name_str
        size = type_full_name_str.split("[")[1].split("]")[0] if is_array else None
        type_val = type_full_name_str.split("[")[0] if is_array else type_full_name_str

        predefined_type = PredefinedIdentifierTypes.get(name)

        return {
            "nodeType": TemplateNodeTypes.Identifier,
            "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
            "name": name,
            "type": predefined_type or type_val,
            "size": size,
            "children": self._converted_children(node.get("children", [])),
        }

    def _handle_return(self, node: TreeNode) -> IReturnStatement:
        """Handle RETURN node."""
        return {
            "nodeType": TemplateNodeTypes.ReturnStatement,
            "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
            "children": self._converted_children(node.get("children", [])),
        }

    def _handle_skipped_nodes(self, node: TreeNode) -> Optional[TemplateNodes]:
        """Handle skipped nodes."""
        return _passthrough_node(node, self._converted_children(node.get("children", [])))

    def _handle_type_decl(self, node: TreeNode) -> Optional[Union[IStructType, ITypeDefinition, IUnionType]]:
        """Handle TYPE_DECL node."""
        properties = node.get("properties", {})
        code = node.get("code", "")

        if "typedef struct" in code:
            return {
                "nodeType": TemplateNodeTypes.StructType,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "name": node.get("name", ""),
                "children": self._converted_children(
                    [
                        child
                        for child in node.get("children", [])
                        if child.get("label") != "METHOD" and child.get("name") != "<clinit>"
                    ]
                ),
            }

        if "typedef union" in code:
            return {
                "nodeType": TemplateNodeTypes.UnionType,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "name": node.get("name", ""),
                "children": self._converted_children(node.get("children", [])),
            }

        if "typedef" in code:
            alias_type_full_name = self._unwrap_graphson_scalar(properties.get("ALIAS_TYPE_FULL_NAME", {}))
            return {
                "nodeType": TemplateNodeTypes.TypeDefinition,
                "id": int(node.get("id", "")) if str(node.get("id", "")).isdigit() else -999,
                "name": node.get("name", ""),
                "underlyingType": str(alias_type_full_name) if alias_type_full_name else "<unknown>",
                "children": self._converted_children(node.get("children", [])),
            }

        # Fallback
        return _passthrough_node(node, self._converted_children(node.get("children", [])))

    def _reshape_label_children(self, children: List[TreeNode]) -> List[TreeNode]:
        """Reshape the children of a switch label node to match the expected structure."""
        reshaped_children: List[TreeNode] = []
        current_label: Optional[TreeNode] = None

        for child in children:
            if child.get("label") == "JUMP_TARGET" and child.get("name") in ["case", "default"]:
                if current_label:
                    reshaped_children.append(current_label)
                current_label = child
            elif current_label:
                if "children" not in current_label:
                    current_label["children"] = []
                current_label["children"].append(child)
            else:
                reshaped_children.append(child)

        if current_label:
            reshaped_children.append(current_label)

        return reshaped_children

    def _unwrap_graphson_scalar(self, value: Any) -> Any:
        """Unwrap a GraphSON property down to the scalar it holds.

        Joern exports vertex properties doubly wrapped::

            {"@type": "g:VertexProperty",
             "@value": {"@type": "g:List", "@value": ["char[64]"]}}

        The previous implementation (named ``_unwrap_graphson_array``) stopped one
        level early and returned the *list*. Callers treat the result as a string,
        so ``re.search`` was handed a list and raised ``expected string or
        bytes-like object, got 'list'`` for any assignment with an
        ``<operator>.alloc`` child -- 37% of the real corpus.

        Multi-valued properties are joined with "/" to match how
        ``_handle_call_operators`` renders address-of types.
        """
        if not isinstance(value, dict):
            return value
        if "@value" not in value:
            return value

        inner = value["@value"]
        if isinstance(inner, dict) and "@value" in inner:
            inner = inner["@value"]

        if isinstance(inner, list):
            if not inner:
                return ""
            if len(inner) == 1:
                return inner[0]
            return "/".join(str(item) for item in inner)
        return inner
