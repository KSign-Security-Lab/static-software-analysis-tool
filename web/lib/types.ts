// Shared types for the F2-A testing web.

// ---- Raw Joern GraphSON (loose) -------------------------------------------

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

// A CPG document as returned by the backend: {"@type","@value":{vertices,edges}}
// (or already-unwrapped {vertices,edges}, or a list of these).
export type CpgDocument = unknown;

// ---- Parsed / normalized CPG ----------------------------------------------

export interface CpgNode {
  id: string;
  label: string; // Joern vertex label (METHOD, CALL, IDENTIFIER, ...)
  name: string;
  code: string;
  line: string | number;
  props: Record<string, unknown>;
}

export interface CpgEdge {
  id: string;
  label: string; // AST, CALL, REACHING_DEF, REF, CFG, DOMINATE, ...
  source: string; // outV
  target: string; // inV
  variable?: string; // REACHING_DEF variable, if present
}

export interface ParsedCpg {
  nodes: Map<string, CpgNode>;
  edges: CpgEdge[];
  edgesByLabel: Map<string, CpgEdge[]>;
  labelCounts: Record<string, number>;
  edgeLabelCounts: Record<string, number>;
  methodOf: (nodeId: string) => string | undefined;
}

// ---- A projected graph view (AST / CG / DFG / CFG / CPG) -------------------

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

/** Views projected straight out of the CPG by edge label (see lib/views.ts). */
export type CpgViewKey = "cpg" | "ast" | "cg" | "dfg" | "cfg";

/** Views built from the SSAT pipeline's own artifacts (see lib/pipeline.ts). */
export type PipelineViewKey = "pipeline-ast" | "pipeline-dfg";

export type ViewKey = CpgViewKey | PipelineViewKey;

export const CPG_VIEW_KEYS: readonly CpgViewKey[] = ["ast", "cfg", "dfg", "cg", "cpg"];
export const PIPELINE_VIEW_KEYS: readonly PipelineViewKey[] = ["pipeline-ast", "pipeline-dfg"];

// ---- SSAT pipeline artifacts ---------------------------------------------
//
// Deliberately distinct from the CPG views above. `ast` is the syntax tree as
// Joern exported it; `pipeline-ast` is the statement-level tree the SSAT
// extractor builds from the Template. Same word, different object -- keeping
// them apart in the type system keeps them apart in the UI.

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
  /** [parent_sid, child_sid, 0] */
  edges_ast_pc: [number, number, number][];
  /** [prev_sid, next_sid, 1] */
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
  /** [src_sid, dst_sid, { feat, debug }] */
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

// ---- F2-A result ----------------------------------------------------------
//
// Generated now, in lib/f2a-schema.ts, from packages/ssat/src/ssat/f2a/models.py
// and drift-tested there. The hand-written mirror that used to live here had
// already gone wrong: F2AResult was missing four of its eleven fields, so
// flow_candidates, sink_mappings, expected_check_matchings and
// missing_check_candidate_sets were invisible to the UI -- and invisible in a
// way TypeScript cannot report, because a property absent from an interface is
// not an error at the point it is read.
//
// Re-exported from here so the ~40 call sites keep one import path.
export type * from "./f2a-schema";
import type { F2AResult } from "./f2a-schema";

/**
 * The `/analyze` envelope.
 *
 * Not generated: the route assembles it by hand in api/main.py rather than
 * returning a pydantic model, so there is nothing to generate it from.
 */
export interface AnalyzeResponse {
  cpg: CpgDocument;
  method_count: number;
  f2a: F2AResult;
}
