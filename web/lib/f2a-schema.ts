// GENERATED FILE -- DO NOT EDIT.
//
// The F2-A result models are defined in packages/ssat/src/ssat/f2a/models.py.
// This file is generated from them by `python -m ssat.schema_ts --write`, and
// packages/ssat/tests/test_schema_ts.py fails if the two drift apart.

export interface ActionIdentifierView {
  protocol_string: string | null;
  symbol: string | null;
  numeric_id: number | null;
  normalized_name: string | null;
  raw_expression: string | null;
  resolved_value: number | string | null;
}

export interface BindingEvidence {
  type: string;
  expression: string;
}

export interface CandidateFragment {
  candidate_id: string;
  candidate_type: "OCPP_NATIVE_CANDIDATE_HVVD_FRAGMENT";
  language: string;
  component_type: string;
  ocpp_context: OcppContext;
  code_evidence: CodeEvidence;
  expected_checks: string[];
  observed_checks: ObservedCheck[];
  missing_check_candidates: MissingCheckItem[];
  root_cause_candidates: string[];
  related_cwe: string[];
  static_confidence: number;
  lifecycle_state_hint: "STATIC_SUSPECT_HVVD" | "REVIEW_READY_HVVD";
  limitations: string[];
}

export interface CheckEvidence {
  expected_checks: string[];
  observed_checks: ObservedCheck[];
  missing_check_candidates: MissingCheckItem[];
}

export interface CodeEvidence {
  source: SourceRef;
  flow: FlowStep[];
  sink: SinkInfo;
}

export interface CodeLocation {
  file: string;
  function: string;
  line: number | string;
}

export interface CompetingCandidateView {
  function: string;
  confidence: number;
  evidence_kinds: string[];
}

export interface ConfidenceBreakdown {
  handler_mapping: number;
  field_binding: number;
  semantic_binding: number;
  source_sink_flow: number;
  sink_mapping: number;
  check_detection: number;
  traceability: number;
  overall_static_confidence: number;
}

export interface ConflictReportView {
  competing: CompetingCandidateView[];
  margin: number;
  note: string;
}

export interface EvidencePackage {
  evidence_id: string;
  candidate_type: "OCPP_NATIVE_EVIDENCE_PACKAGE";
  language: string;
  component_type: string;
  ocpp_context: OcppContext;
  code_evidence: CodeEvidence;
  check_evidence: CheckEvidence;
  traceability: Traceability;
  security_interpretation: SecurityInterpretation;
  root_cause_candidates: string[];
  related_cwe: string[];
  confidence: ConfidenceBreakdown;
  static_confidence: number;
  limitations: string[];
}

export interface EvidenceRecord {
  type: string;
  value: string;
  file: string;
  line: number | string;
}

export interface ExpectedCheckMatching {
  expected_check_matching_id: string;
  candidate_id: string;
  action: string;
  field: string;
  field_semantic: string;
  expected_checks: string[];
  observed_check_references: string[];
  matching_results: MatchingResult[];
  missing_check_summary: MissingCheckSummary;
}

export interface FieldBinding {
  field_binding_id: string;
  action: string;
  field: string;
  field_semantic: string;
  binding: FieldBindingDetail;
  binding_evidence: BindingEvidence[];
  confidence: number;
}

export interface FieldBindingDetail {
  source_type: string;
  source_expression: string;
  bound_variable: string;
  file: string;
  function: string;
  line: number | string;
}

export interface FlowCandidate {
  candidate_id: string;
  language: string;
  component_type: string;
  ocpp_version: string;
  action: string;
  field: string;
  field_semantic: string;
  source: SourceRef;
  flow: FlowStep[];
  sink: SinkInfo;
  observed_checks: string[];
  expected_checks: string[];
  missing_check_candidates: string[];
  static_confidence: number;
  limitations: string[];
}

export interface FlowStep {
  step: number;
  function: string;
  file: string;
  line: number | string;
  operation: string;
}

export interface HandlerMap {
  handler_map_id: string;
  action: string;
  handler: HandlerRef;
  mapping_evidence: MappingEvidence[];
  confidence: number;
}

export interface HandlerRef {
  file: string;
  function: string;
  line: number | string;
  language: string;
}

export interface HandlerResolution {
  action: string;
  status: string;
  chosen: HandlerRef | null;
  candidates: HandlerResolutionCandidate[];
  conflict: ConflictReportView | null;
  unresolved: UnresolvedReportView | null;
}

export interface HandlerResolutionCandidate {
  function: string;
  file: string;
  line: number | string;
  confidence: number;
  evidence_kinds: string[];
  action_id_consistency: string;
  evidence: HandlerResolutionEvidence[];
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

export interface MappingEvidence {
  type: string;
  value: string;
  file: string;
  line: number | string;
}

export interface MatchingResult {
  expected_check: string;
  matching_status: "SATISFIED" | "PARTIALLY_SATISFIED" | "WEAKLY_RELATED" | "UNVERIFIED" | "NEGATIVE_EVIDENCE_FOUND" | "CONFLICTED" | "REVIEW_REQUIRED";
  matched_observed_check: string | null;
  check_strength: "STRONG" | "PARTIAL" | "WEAK" | "UNKNOWN" | "CONFLICTED" | null;
  basis: string[];
  confidence: number;
  limitations: string[];
}

export interface MissingCheckCandidateSet {
  missing_check_candidate_id: string;
  candidate_id: string;
  action: string;
  field: string;
  missing_check_candidates: MissingCheckItem[];
  weak_or_partial_check_candidates: WeakCheckItem[];
  review_required_missing_check_candidates: MissingCheckItem[];
  limitations: string[];
}

export interface MissingCheckItem {
  check_id: string;
  basis: string;
  confidence: number;
  reason: string;
}

export interface MissingCheckSummary {
  satisfied_checks: string[];
  partially_satisfied_checks: string[];
  weakly_related_checks: string[];
  missing_check_candidates: string[];
  review_required_checks: string[];
}

export interface ObservedCheck {
  observed_check_id: string;
  detection_method: "RULE_BASED" | "LLM_ASSISTED";
  check_type: string;
  action: string;
  field: string;
  applies_to: string[];
  file: string;
  function: string;
  line: number | string;
  evidence: string;
  check_strength: "STRONG" | "PARTIAL" | "WEAK" | "UNKNOWN" | "CONFLICTED";
  matched_expected_check: string | null;
  confidence: number;
}

export interface OcppContext {
  ocpp_version: string;
  action: string;
  field: string;
  field_semantic: string;
  trust_level: string;
}

export interface PrimaryLocation {
  file: string;
  line: number | string;
  evidence: string;
}

export interface SecurityInterpretation {
  summary: string;
  root_cause_candidates: string[];
  related_cwe: string[];
}

export interface SinkInfo {
  sink_domain: string;
  api: string;
  file: string;
  function: string;
  line: number | string;
}

export interface SinkMapping {
  sink_mapping_id: string;
  sink: CodeLocation;
  api: string;
  sink_domain: string;
  related_cwe: string[];
  severity_hint: string;
  mapping_evidence: string[];
}

export interface SourceRef {
  source_type: string;
  binding: string;
  file: string;
  function: string;
  line: number | string;
}

export interface Traceability {
  files: string[];
  functions: string[];
  primary_locations: PrimaryLocation[];
}

export interface UnresolvedDispatchSite {
  file: string;
  line: number | string;
  code: string;
}

export interface UnresolvedReportView {
  reason: string;
  secondary: string | null;
  dispatch_site: UnresolvedDispatchSite | null;
  attempted_extractors: string[];
}

export interface WeakCheckItem {
  check_id: string;
  related_expected_check: string | null;
  reason: string;
}

export interface F2AResult {
  source_cpg: string;
  handler_maps: HandlerMap[];
  handler_resolutions: HandlerResolution[];
  field_bindings: FieldBinding[];
  flow_candidates: FlowCandidate[];
  sink_mappings: SinkMapping[];
  expected_check_matchings: ExpectedCheckMatching[];
  missing_check_candidate_sets: MissingCheckCandidateSet[];
  evidence_packages: EvidencePackage[];
  candidate_fragments: CandidateFragment[];
  limitations: string[];
}
