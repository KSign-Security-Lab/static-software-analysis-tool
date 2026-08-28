"""CPG validation using Pydantic."""

from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field


class GraphSONNumber(BaseModel):
    """GraphSON number wrapper."""

    type_: str = Field(alias="@type")
    value_: Union[int, float] = Field(alias="@value")


class EdgeSchema(BaseModel):
    """Edge schema."""

    type_: str = Field(alias="@type")
    id: GraphSONNumber
    inV: GraphSONNumber
    inVLabel: str
    label: str
    outV: GraphSONNumber
    outVLabel: str
    properties: Dict[str, Any]


class VertexSchema(BaseModel):
    """Vertex schema."""

    type_: str = Field(alias="@type")
    id: GraphSONNumber
    label: str
    properties: Dict[str, Any]


class GraphDataSchema(BaseModel):
    """Graph data schema."""

    edges: List[EdgeSchema]
    vertices: List[VertexSchema]


class GraphSONWrapper(BaseModel):
    """GraphSON wrapper."""

    type_: str = Field(alias="@type")
    value_: GraphDataSchema = Field(alias="@value")


def validate_cpg_root(input_data: Any) -> Union[GraphSONWrapper, List[GraphSONWrapper]]:
    """
    Parse and validate unknown JSON.
    Accepts either a single GraphSON object or an array of them.
    """
    if isinstance(input_data, list):
        return [GraphSONWrapper.model_validate(item) for item in input_data]
    return GraphSONWrapper.model_validate(input_data)
