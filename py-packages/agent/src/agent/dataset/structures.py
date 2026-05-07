from __future__ import annotations
from typing import Any, ClassVar, Dict, List, Optional, Union
from pydantic import BaseModel, Field, ConfigDict
from pydantic import BaseModel, Field


class NodeModel(BaseModel):
    """Default node container."""

    id: Optional[int] = None
    feat: Optional[Dict[str, Any]] = None

    # Pydantic-config keys only (type-safe for Pyright)
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


class EdgeModel(BaseModel):
    """Default edge with optional scalar attr."""

    src: int
    dst: int
    attr: Optional[Union[int, float]] = 0

    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")


class BaseGraphModel(BaseModel):
    """
    Base graph model.

    Define your node/edge fields freely, then declare how to read them in a *separate*
    class var `graph_config`, e.g.:

        class MyGraph(BaseGraphModel):
            nodes_func: List[...]=[]
            nodes_var:  List[...]=[]
            edges_ast:  List[...]=[]
            edges_dfg:  List[...]=[]
            graph_config = {
                "node_keys": ["nodes_func", "nodes_var"],
                "edge_keys": {"ast": "edges_ast", "dfg": "edges_dfg"},
            }

    This avoids overriding pydantic's `model_config` with non-ConfigDict keys.
    """

    # Convenient defaults; you can override via subclass and `graph_config`.
    nodes: List[Union[NodeModel, Dict[str, Any]]] = Field(default_factory=list)
    edges: Optional[List[Union[EdgeModel, Dict[str, Any], List[int]]]] = None

    # Keep ONLY valid pydantic keys here
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="allow")

    # Custom dataset config lives here (safe for Pyright)
    graph_config: ClassVar[Dict[str, Any]] = {
        "node_keys": ["nodes"],
        "edge_keys": ["edges"],
    }
