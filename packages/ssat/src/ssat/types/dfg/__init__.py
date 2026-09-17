from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

from ..template.BaseNode.base_types import TemplateNodeTypes


class FlowType(str, Enum):
    BASE = "BASE"
    INDEX = "INDEX"
    SIZE = "SIZE"
    VALUE = "VALUE"


class GuardType(str, Enum):
    IF = "IF"
    LOOP = "LOOP"
    NONE = "NONE"


class IDFGEdgeFeature(TypedDict):
    flow: FlowType
    guard: GuardType
    hasLowerGuard: bool
    hasUpperGuard: bool
    upperGuardNormalization: float


class IDFGNodeFeature(TypedDict):
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
    sid: int
    id: int
    features: IDFGNodeFeature
    debug: Optional[Dict[str, Any]]


class IDFGEdge(TypedDict):
    source: int
    destination: int
    features: IDFGEdgeFeature
    debug: Optional[Dict[str, Any]]


class IDFGGraph(TypedDict):
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
