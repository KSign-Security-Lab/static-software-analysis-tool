from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict, Union

from pydantic import BaseModel, Field

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

GraphSONValue = Union[bool, List["GraphSONValue"], None, int, float, str, Dict[str, "GraphSONValue"]]


class GraphSON(BaseModel):
    type_name: str = Field(alias="@type")
    value: Dict[str, Any] = Field(alias="@value")


class EdgeGraphSON(BaseModel):
    type_name: str = Field(alias="@type")
    value: Any = Field(alias="@value")


class VertexGeneric(BaseModel):
    type_name: str = Field(alias="@type")
    id: EdgeGraphSON
    label: VertexLabel
    properties: Dict[str, Any]


class EdgeGeneric(BaseModel):
    type_name: str = Field(alias="@type")
    id: EdgeGraphSON
    inV: EdgeGraphSON
    inVLabel: VertexLabel
    label: EdgeLabel
    outV: EdgeGraphSON
    outVLabel: VertexLabel
    properties: Dict[str, Any]


class CPGGraphData(BaseModel):
    edges: List[EdgeGeneric]
    vertices: List[VertexGeneric]


class ICPGRootExport(BaseModel):
    type_name: str = Field(alias="@type")
    value: Union[CPGGraphData, Dict[str, Any]] = Field(alias="@value")


class CPGRoot(TypedDict):
    export: Dict[str, Any]


class NodeInfo(TypedDict):
    code: str
    id: str
    label: str
    line_no: Union[int, str]
    name: str
    properties: Dict[str, Any]


class TreeNode(NodeInfo):
    children: List["TreeNode"]
