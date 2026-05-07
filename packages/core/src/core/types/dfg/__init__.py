"""DFG type definitions."""

from enum import Enum
from typing import List, Optional, TypedDict

from ..template.BaseNode.base_types import TemplateNodeTypes


class FlowType(str, Enum):
    """Flow type enumeration."""

    BASE = "BASE"
    INDEX = "INDEX"
    SIZE = "SIZE"
    VALUE = "VALUE"


class GuardType(str, Enum):
    """Guard type enumeration."""

    IF = "IF"
    LOOP = "LOOP"
    NONE = "NONE"


class IDFGEdgeFeature(TypedDict):
    """DFG edge feature structure."""

    flow: FlowType
    guard: GuardType
    hasLowerGuard: bool
    hasUpperGuard: bool
    upperGuardNormalization: float


class IDFGNodeFeature(TypedDict):
    """DFG node feature structure."""

    nodeType: TemplateNodeTypes
    inDegreeDFG: int
    outDegreeDFG: int
    defCount: int
    useCount: int
    isBufferAccess: bool
    isSinkAssignment: bool
    isSinkCallUnbounded: bool
    isSinkCallBounded: bool
    callDestinationIndexed: bool
    callLengthLinkedToDestination: bool
    callSizeNonConstant: bool
    callDangerUnbounded: bool


class IDFGNode(TypedDict):
    """DFG node structure."""

    sid: int
    id: int
    features: IDFGNodeFeature
    debug: Optional[dict]


class IDFGEdge(TypedDict):
    """DFG edge structure."""

    source: int
    destination: int
    features: IDFGEdgeFeature
    debug: Optional[dict]


class IDFGGraph(TypedDict):
    """DFG graph structure."""

    nodes: List[IDFGNode]
    edges: List[IDFGEdge]


__all__ = [
    "FlowType",
    "GuardType",
    "IDFGEdgeFeature",
    "IDFGNodeFeature",
    "IDFGNode",
    "IDFGEdge",
    "IDFGGraph",
]


