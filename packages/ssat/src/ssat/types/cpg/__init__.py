"""CPG type definitions."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict, Union

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

GraphSONValue = Union[bool, List["GraphSONValue"], None, int, float, str, Dict[str, "GraphSONValue"]]


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


# The three types below are TypedDicts rather than pydantic models because
# nothing ever constructs or validates them -- the pipeline builds plain dicts
# and reads them with .get()/[...]. Declaring them as BaseModel made every one
# of those accesses a type error while changing nothing at runtime. Structural
# validation of incoming CPGs is done by GraphSONWrapper in ssat.cpg.validate.


class CPGRoot(TypedDict):
    """A CPG document: the joern-export GraphSON under an ``export`` key."""

    export: Dict[str, Any]


class NodeInfo(TypedDict):
    """A CPG vertex flattened to the fields the template stage needs."""

    code: str
    id: str
    label: str
    line_no: Union[int, str]
    name: str
    properties: Dict[str, Any]


class TreeNode(NodeInfo):
    """A :class:`NodeInfo` with its AST children attached."""

    children: List["TreeNode"]
