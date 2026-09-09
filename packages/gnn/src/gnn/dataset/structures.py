from __future__ import annotations
from typing import Any, ClassVar, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict


class NodeModel(BaseModel):
    id: Optional[int] = None
    feat: Optional[Dict[str, Any]] = None
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


class EdgeModel(BaseModel):
    src: int
    dst: int
    attr: Optional[Union[int, float]] = 0
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


class BaseGraphModel(BaseModel):
    nodes: List[Union[NodeModel, Dict[str, Any]]] = Field(default_factory=list)
    edges: Optional[List[Union[EdgeModel, Dict[str, Any], List[int]]]] = None
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")
    graph_config: ClassVar[Dict[str, Any]] = {
        "node_keys": ["nodes"],
        "edge_keys": ["edges"],
    }
