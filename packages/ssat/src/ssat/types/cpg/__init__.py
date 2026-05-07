"""CPG type definitions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field

# Type aliases
EdgeLabel = Literal[
    "ALIAS_OF",
    "ARGUMENT",
    "AST",
    "BINDS",
    "CALL",
    "CDG",
    "CFG",
    "CONDITION",
    "CONTAINS",
    "DOMINATE",
    "EVAL_TYPE",
    "IMPORTS",
    "PARAMETER_LINK",
    "POST_DOMINATE",
    "REACHING_DEF",
    "REF",
    "SOURCE_FILE",
]

VertexLabel = Literal[
    "BINDING",
    "BLOCK",
    "CALL",
    "CONTROL_STRUCTURE",
    "DEPENDENCY",
    "FIELD_IDENTIFIER",
    "FILE",
    "IDENTIFIER",
    "IMPORT",
    "JUMP_TARGET",
    "LITERAL",
    "LOCAL",
    "MEMBER",
    "META_DATA",
    "METHOD",
    "METHOD_PARAMETER_IN",
    "METHOD_PARAMETER_OUT",
    "METHOD_REF",
    "METHOD_RETURN",
    "MODIFIER",
    "NAMESPACE",
    "NAMESPACE_BLOCK",
    "RETURN",
    "TYPE",
    "TYPE_DECL",
    "TYPE_REF",
    "UNKNOWN",
]

GraphSONValue = Union[
    bool, List["GraphSONValue"], None, int, float, str, Dict[str, "GraphSONValue"]
]


class GraphSON(BaseModel):
    """GraphSON wrapper type."""

    type_name: str = Field(alias="@type")
    value: Dict[str, Any] = Field(alias="@value")


class EdgeGraphSON(BaseModel):
    """Edge GraphSON type."""

    type_name: str = Field(alias="@type")
    value: Any = Field(alias="@value")


class VertexGeneric(BaseModel):
    """Generic vertex type."""

    type_name: str = Field(alias="@type")
    id: EdgeGraphSON
    label: VertexLabel
    properties: Dict[str, Any]


class EdgeGeneric(BaseModel):
    """Generic edge type."""

    type_name: str = Field(alias="@type")
    id: EdgeGraphSON
    inV: EdgeGraphSON
    inVLabel: VertexLabel
    label: EdgeLabel
    outV: EdgeGraphSON
    outVLabel: VertexLabel
    properties: Dict[str, Any]


class CPGGraphData(BaseModel):
    """CPG graph data structure."""

    edges: List[EdgeGeneric]
    vertices: List[VertexGeneric]


class ICPGRootExport(BaseModel):
    """CPG root export structure."""

    type_name: str = Field(alias="@type")
    value: Union[CPGGraphData, Dict[str, Any]] = Field(alias="@value")


class CPGRoot(BaseModel):
    """CPG root structure."""

    export: Union[ICPGRootExport, Dict[str, Any]]


class NodeInfo(BaseModel):
    """Node information structure."""

    code: str
    id: str
    label: VertexLabel
    line_no: Union[int, str]
    name: str
    properties: Dict[str, Any]


class TreeNode(NodeInfo):
    """Tree node with children."""

    children: List[TreeNode]
