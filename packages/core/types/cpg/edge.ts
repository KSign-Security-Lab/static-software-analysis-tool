// edge.ts
import { VertexLabel } from "./index";

export type AliasOfEdgeProperties = object;
export type ArgumentEdgeProperties = object;
export type AstEdgeProperties = object;
export type BindsEdgeProperties = object;
export type CallEdgeProperties = object;
export type CdgEdgeProperties = object;
export type CfgEdgeProperties = object;
export type ConditionEdgeProperties = object;
export type ContainsEdgeProperties = object;
export type DominateEdgeProperties = object;

export interface EdgeByLabelMap {
  ALIAS_OF: AliasOfEdgeProperties;
  ARGUMENT: ArgumentEdgeProperties;
  AST: AstEdgeProperties;
  BINDS: BindsEdgeProperties;
  CALL: CallEdgeProperties;
  CDG: CdgEdgeProperties;
  CFG: CfgEdgeProperties;
  CONDITION: ConditionEdgeProperties;
  CONTAINS: ContainsEdgeProperties;
  DOMINATE: DominateEdgeProperties;
  EVAL_TYPE: EvalTypeEdgeProperties;
  IMPORTS: ImportsEdgeProperties;
  PARAMETER_LINK: ParameterLinkEdgeProperties;
  POST_DOMINATE: PostDominateEdgeProperties;
  REACHING_DEF: ReachingDefEdgeProperties;
  REF: RefEdgeProperties;
  SOURCE_FILE: SourceFileEdgeProperties;
}
export interface EdgeGeneric<L extends keyof EdgeByLabelMap = keyof EdgeByLabelMap> {
  "@type": string;
  id: EdgeGraphSON<number>;
  inV: EdgeGraphSON<number>;
  inVLabel: VertexLabel;
  label: L;
  outV: EdgeGraphSON<number>;
  outVLabel: VertexLabel;
  properties: EdgeByLabelMap[L];
}
export interface EdgeGraphSON<T> {
  "@type": string;
  "@value": T;
}

export type EvalTypeEdgeProperties = object;

export type ImportsEdgeProperties = object;

export type ParameterLinkEdgeProperties = object;

export type PostDominateEdgeProperties = object;

export interface ReachingDefEdgeProperties {
  EdgeProperty: EdgeGraphSON<string>;
}

export type RefEdgeProperties = object;

export type SourceFileEdgeProperties = object;
