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

export type ViewKey = "cpg" | "ast" | "cg" | "dfg" | "cfg";

// ---- F2-A result (subset we render; the rest is passed through) -----------

export interface F2AResult {
  source_cpg?: string;
  handler_maps: HandlerMap[];
  field_bindings: FieldBinding[];
  evidence_packages: EvidencePackage[];
  candidate_fragments: CandidateFragment[];
  limitations: string[];
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
