export type GraphSonValue = unknown;

export interface RawVertex {
  id: GraphSonValue;
  label: string;
  properties?: Record<string, GraphSonValue>;
}

export interface RawEdge {
  id: GraphSonValue;
  label: string;
  inV: GraphSonValue;
  inVLabel?: string;
  outV: GraphSonValue;
  outVLabel?: string;
  properties?: Record<string, GraphSonValue>;
}

export interface RawGraph {
  vertices: RawVertex[];
  edges: RawEdge[];
}

export type CpgDocument = unknown;

export interface CpgNode {
  id: string;
  label: string;
  name: string;
  code: string;
  line: string | number;
  props: Record<string, unknown>;
}

export interface CpgEdge {
  id: string;
  label: string;
  source: string;
  target: string;
  variable?: string;
}

export interface ParsedCpg {
  nodes: Map<string, CpgNode>;
  edges: CpgEdge[];
  edgesByLabel: Map<string, CpgEdge[]>;
  labelCounts: Record<string, number>;
  edgeLabelCounts: Record<string, number>;
  methodOf: (nodeId: string) => string | undefined;
}

export interface ViewNode {
  id: string;
  label: string;
  name: string;
  code: string;
  line: string | number;
  props: Record<string, unknown>;
}

export interface ViewEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

export interface GraphView {
  key: ViewKey;
  title: string;
  description: string;
  nodes: ViewNode[];
  edges: ViewEdge[];
}

export type CpgViewKey = "cpg" | "ast" | "cg" | "dfg" | "cfg";

export type PipelineViewKey = "pipeline-ast" | "pipeline-dfg";

export type ViewKey = CpgViewKey | PipelineViewKey;

export const CPG_VIEW_KEYS: readonly CpgViewKey[] = ["ast", "cfg", "dfg", "cg", "cpg"];
export const PIPELINE_VIEW_KEYS: readonly PipelineViewKey[] = ["pipeline-ast", "pipeline-dfg"];

export interface PipelineAstNode {
  sid: number;
  node_type_id: string;
  code: string;
  orig_id?: number;
  feat?: Record<string, unknown>;
  debug?: Record<string, unknown>;
}

export interface PipelineAst {
  nodes: PipelineAstNode[];
  edges_ast_pc: [number, number, number][];
  edges_ast_sb: [number, number, number][];
  edges_ast_guard: { src: number; dst: number; guard_kind: number; guard_branch: unknown }[];
}

export interface PipelineDfgNode {
  sid: number;
  node_type_id?: string;
  feat?: Record<string, unknown>;
  debug?: Record<string, unknown>;
}

export interface PipelineDfg {
  nodes: PipelineDfgNode[];
  edges_dfg: [number, number, { feat?: Record<string, unknown>; debug?: Record<string, unknown> }][];
}

export interface PipelineFunction {
  function_name: string;
  source_template?: string;
  code?: string;
  ast: PipelineAst;
  dfg: PipelineDfg;
}

export interface PipelineResponse {
  functions: PipelineFunction[];
}

export type * from "./f2a-schema";
import type { F2AResult } from "./f2a-schema";

export interface AnalyzeResponse {
  cpg: CpgDocument;
  method_count: number;
  f2a: F2AResult;
}
