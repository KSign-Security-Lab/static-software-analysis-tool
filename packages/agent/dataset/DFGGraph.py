from typing import Any, Dict, List, Literal, NotRequired, TypedDict

DFGNodeType = Literal[
    "FunctionEntry",
    "AssignmentExpression",
    "StandardLibCall",
    "UserDefinedCall",
    "ParameterDeclaration",
]

DFGFlowType = Literal["BASE", "INDEX"]
DFGGuardType = Literal["NONE"]
DFGLabelType = Literal["METHOD", "CALL", "METHOD_PARAMETER_IN"]


class DFGNodeFeatures(TypedDict):
    nodeType: DFGNodeType
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


class DFGNodeDebug(TypedDict):
    label: DFGLabelType
    code: str
    type: str
    file: str
    # Optional fields (present for CALL/METHOD nodes variably)
    callName: NotRequired[str]
    argCount: NotRequired[int]
    reason: NotRequired[str]


class DFGNode(TypedDict):
    id: int
    features: DFGNodeFeatures
    debug: DFGNodeDebug


class DFGEdgeFeatures(TypedDict):
    flow: DFGFlowType
    guard: DFGGuardType
    hasLowerGuard: bool
    hasUpperGuard: bool
    upperGuardNormalization: int


class DFGEdgeDebug(TypedDict):
    srcCode: str
    dstCode: str
    call: str
    guard: Dict[str, Any]


class DFGEdge(TypedDict):
    source: int
    destination: int
    features: DFGEdgeFeatures
    debug: DFGEdgeDebug


class DFGGraph(TypedDict):
    nodes: List[DFGNode]
    edges: List[DFGEdge]


DFG = List[DFGGraph]
