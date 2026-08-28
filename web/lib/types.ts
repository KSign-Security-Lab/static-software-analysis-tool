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

// ---- F2-A result (subset we render; the rest is passed through) -----------

export interface F2AResult {
  source_cpg?: string;
  handler_maps: HandlerMap[];
  handler_resolutions?: HandlerResolution[];
  field_bindings: FieldBinding[];
  evidence_packages: EvidencePackage[];
  candidate_fragments: CandidateFragment[];
  limitations: string[];
}

// Authoritative per-action resolution outcome (mirrors the backend public model).
export type ResolutionStatus = "RESOLVED" | "AMBIGUOUS" | "UNRESOLVED";

export interface ActionIdentifierView {
  protocol_string?: string | null;
  symbol?: string | null;
  numeric_id?: number | null;
  normalized_name?: string | null;
  raw_expression?: string | null;
  resolved_value?: number | string | null;
}

export interface EvidenceRecord {
  type: string; // DISPATCH_*, HANDLER_REF, ACTION_STORE, SLOT, CHAIN_CALL, CHAIN_STORE, ...
  value: string;
  file: string;
  line: string | number;
}

export interface HandlerResolutionEvidence {
  kind: string;
  extractor: string;
  match_strength: string;
  action_id_consistency: string;
  provenance_group: string;
  weight: number;
  score: number;
  score_pre_penalty: number;
  action_id: ActionIdentifierView;
  dispatch_site: UnresolvedDispatchSite | null;
  records: EvidenceRecord[];
}

export interface HandlerResolutionCandidate {
  function: string;
  file: string;
  line: string | number;
  confidence: number;
  evidence_kinds: string[];
  action_id_consistency: string; // CONSISTENT | CONFLICTING | PARTIAL
  evidence?: HandlerResolutionEvidence[];
}

export interface CompetingCandidateView {
  function: string;
  confidence: number;
  evidence_kinds: string[];
}

export interface ConflictReportView {
  competing: CompetingCandidateView[];
  margin: number;
  note: string;
}

export interface UnresolvedDispatchSite {
  file: string;
  line: string | number;
  code: string;
}

export interface UnresolvedReportView {
  reason: string;
  secondary: string | null;
  dispatch_site: UnresolvedDispatchSite | null;
  attempted_extractors: string[];
}

export interface HandlerResolution {
  action: string;
  status: ResolutionStatus;
  chosen: { file: string; function: string; line: string | number; language?: string } | null;
  candidates: HandlerResolutionCandidate[];
  conflict: ConflictReportView | null;
  unresolved: UnresolvedReportView | null;
}

export interface HandlerMap {
  handler_map_id: string;
  action: string;
  handler: { file: string; function: string; line: string | number; language: string };
  mapping_evidence: { type: string; value: string; file: string; line: string | number }[];
  confidence: number;
}

export interface FieldBinding {
  field_binding_id: string;
  action: string;
  field: string;
  field_semantic: string;
  binding: {
    source_expression: string;
    bound_variable: string;
    file: string;
    function: string;
    line: string | number;
  };
  confidence: number;
}

export interface FlowStep {
  step: number;
  function: string;
  file: string;
  line: string | number;
  operation: string;
}

export interface ObservedCheck {
  observed_check_id: string;
  check_type: string;
  check_strength: string;
  matched_expected_check: string | null;
  evidence: string;
  file: string;
  function: string;
  line: string | number;
  confidence: number;
}

export interface MissingCheckItem {
  check_id: string;
  basis: string;
  confidence: number;
  reason: string;
}

export interface EvidencePackage {
  evidence_id: string;
  language: string;
  component_type: string;
  ocpp_context: {
    ocpp_version: string;
    action: string;
    field: string;
    field_semantic: string;
    trust_level: string;
  };
  code_evidence: {
    source: { binding: string; file: string; function: string; line: string | number };
    flow: FlowStep[];
    sink: { sink_domain: string; api: string; file: string; function: string; line: string | number };
  };
  check_evidence: {
    expected_checks: string[];
    observed_checks: ObservedCheck[];
    missing_check_candidates: MissingCheckItem[];
  };
  security_interpretation: { summary: string; root_cause_candidates: string[]; related_cwe: string[] };
  related_cwe: string[];
  confidence: {
    handler_mapping: number;
    field_binding: number;
    semantic_binding: number;
    source_sink_flow: number;
    sink_mapping: number;
    check_detection: number;
    traceability: number;
    overall_static_confidence: number;
  };
  static_confidence: number;
  limitations: string[];
}

export interface CandidateFragment {
  candidate_id: string;
  lifecycle_state_hint: string;
}

export interface AnalyzeResponse {
  cpg: CpgDocument;
  method_count: number;
  f2a: F2AResult;
}
