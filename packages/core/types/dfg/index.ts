import { ASTNodeTypes } from "../ast/BaseNode/BaseNode";

export enum FlowType {
  BASE = "BASE",
  INDEX = "INDEX",
  SIZE = "SIZE",
  VALUE = "VALUE",
}

export enum GuardType {
  IF = "IF",
  LOOP = "LOOP",
  NONE = "NONE",
}

export interface IDFGEdgeFeature {
  flow: FlowType;
  guard: GuardType;
  hasLowerGuard: boolean;
  hasUpperGuard: boolean;
  upperGuardNormalization: number;
}

export interface IDFGNodeFeature {
  nodeType: ASTNodeTypes;
  inDegreeDFG: number;
  outDegreeDFG: number;
  defCount: number;
  useCount: number;
  isBufferAccess: boolean;
  isSinkAssignment: boolean;
  isSinkCallUnbounded: boolean;
  isSinkCallBounded: boolean;
  callDestinationIndexed: boolean;
  callLengthLinkedToDestination: boolean;
  callSizeNonConstant: boolean;
  callDangerUnbounded: boolean;
}

export interface IDFGNode {
  id: number;
  features: IDFGNodeFeature;
  debug?: Record<string, unknown>;
}

export interface IDFGEdge {
  source: number;
  destination: number;
  features: IDFGEdgeFeature;
  debug?: Record<string, unknown>;
}

export interface IDFGGraph {
  nodes: IDFGNode[];
  edges: IDFGEdge[];
}
