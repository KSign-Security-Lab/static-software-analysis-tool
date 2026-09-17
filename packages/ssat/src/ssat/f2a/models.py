from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


SinkDomain = Literal[
    "COMMAND_EXECUTION",
    "UNSAFE_FIRMWARE_DOWNLOAD",
    "UNSAFE_EXTERNAL_RESOURCE",
    "FILE_WRITE",
    "CONFIGURATION_MUTATION",
    "AUTHORIZATION_DECISION",
    "TRANSACTION_STATE_CHANGE",
    "CONNECTOR_CONTROL",
    "MEMORY_UNSAFE_OPERATION",
    "LOG/DIAGNOSTIC_EXPORT",
    "REMOTE_COMMAND_DISPATCH",
    "FIRMWARE_INSTALL",
    "UPDATE_ACTIVATION",
    "database_query_execution",
]

CheckStrength = Literal["STRONG", "PARTIAL", "WEAK", "UNKNOWN", "CONFLICTED"]
MatchingStatus = Literal[
    "SATISFIED",
    "PARTIALLY_SATISFIED",
    "WEAKLY_RELATED",
    "UNVERIFIED",
    "NEGATIVE_EVIDENCE_FOUND",
    "CONFLICTED",
    "REVIEW_REQUIRED",
]

DetectionMethod = Literal["RULE_BASED", "LLM_ASSISTED"]
LifecycleStateHint = Literal["STATIC_SUSPECT_HVVD", "REVIEW_READY_HVVD"]


class CodeLocation(BaseModel):
    file: str = ""
    function: str = ""
    line: Union[int, str] = ""


class MappingEvidence(BaseModel):
    type: str
    value: str = ""
    file: str = ""
    line: Union[int, str] = ""


class HandlerRef(CodeLocation):
    language: str = "c"


class HandlerMap(BaseModel):
    handler_map_id: str
    action: str
    handler: HandlerRef
    mapping_evidence: List[MappingEvidence] = Field(default_factory=list)
    confidence: float = 0.0


class UnresolvedDispatchSite(BaseModel):
    file: str = ""
    line: Union[int, str] = ""
    code: str = ""


class ActionIdentifierView(BaseModel):
    protocol_string: Optional[str] = None
    symbol: Optional[str] = None
    numeric_id: Optional[int] = None
    normalized_name: Optional[str] = None
    raw_expression: Optional[str] = None
    resolved_value: Optional[Union[int, str]] = None


class EvidenceRecord(BaseModel):
    type: str
    value: str = ""
    file: str = ""
    line: Union[int, str] = ""


class HandlerResolutionEvidence(BaseModel):
    kind: str
    extractor: str = ""
    match_strength: str = ""
    action_id_consistency: str = "PARTIAL"
    provenance_group: str = ""
    weight: float = 0.0
    score: float = 0.0
    score_pre_penalty: float = 0.0
    action_id: ActionIdentifierView = Field(default_factory=ActionIdentifierView)
    dispatch_site: Optional[UnresolvedDispatchSite] = None
    records: List[EvidenceRecord] = Field(default_factory=list)


class HandlerResolutionCandidate(BaseModel):
    function: str = ""
    file: str = ""
    line: Union[int, str] = ""
    confidence: float = 0.0
    evidence_kinds: List[str] = Field(default_factory=list)
    action_id_consistency: str = "PARTIAL"
    evidence: List[HandlerResolutionEvidence] = Field(default_factory=list)


class CompetingCandidateView(BaseModel):
    function: str = ""
    confidence: float = 0.0
    evidence_kinds: List[str] = Field(default_factory=list)


class ConflictReportView(BaseModel):
    competing: List[CompetingCandidateView] = Field(default_factory=list)
    margin: float = 0.0
    note: str = ""


class UnresolvedReportView(BaseModel):
    reason: str = ""
    secondary: Optional[str] = None
    dispatch_site: Optional[UnresolvedDispatchSite] = None
    attempted_extractors: List[str] = Field(default_factory=list)


class HandlerResolution(BaseModel):
    action: str
    status: str
    chosen: Optional[HandlerRef] = None
    candidates: List[HandlerResolutionCandidate] = Field(default_factory=list)
    conflict: Optional[ConflictReportView] = None
    unresolved: Optional[UnresolvedReportView] = None


class BindingEvidence(BaseModel):
    type: str
    expression: str = ""


class FieldBindingDetail(BaseModel):
    source_type: str = "OCPP_PAYLOAD_FIELD"
    source_expression: str = ""
    bound_variable: str = ""
    file: str = ""
    function: str = ""
    line: Union[int, str] = ""


class FieldBinding(BaseModel):
    field_binding_id: str
    action: str
    field: str
    field_semantic: str = ""
    binding: FieldBindingDetail
    binding_evidence: List[BindingEvidence] = Field(default_factory=list)
    confidence: float = 0.0


class SemanticBinding(BaseModel):
    field_semantic: str = ""
    trust_level: str = ""
    expected_checks: List[str] = Field(default_factory=list)
    dangerous_sink_domains: List[str] = Field(default_factory=list)
    related_cwe: List[str] = Field(default_factory=list)
    validation_requirement: List[str] = Field(default_factory=list)


class FlowStep(BaseModel):
    step: int
    function: str = ""
    file: str = ""
    line: Union[int, str] = ""
    operation: str = ""


class SourceRef(BaseModel):
    source_type: str = "OCPP_PAYLOAD_FIELD"
    binding: str = ""
    file: str = ""
    function: str = ""
    line: Union[int, str] = ""


class SinkInfo(BaseModel):
    sink_domain: str = ""
    api: str = ""
    file: str = ""
    function: str = ""
    line: Union[int, str] = ""


class SinkMapping(BaseModel):
    sink_mapping_id: str
    sink: CodeLocation
    api: str = ""
    sink_domain: str = ""
    related_cwe: List[str] = Field(default_factory=list)
    severity_hint: str = ""
    mapping_evidence: List[str] = Field(default_factory=list)


class ObservedCheck(BaseModel):
    observed_check_id: str
    detection_method: DetectionMethod = "RULE_BASED"
    check_type: str = ""
    action: str = ""
    field: str = ""
    applies_to: List[str] = Field(default_factory=list)
    file: str = ""
    function: str = ""
    line: Union[int, str] = ""
    evidence: str = ""
    check_strength: CheckStrength = "UNKNOWN"
    matched_expected_check: Optional[str] = None
    confidence: float = 0.0


class NegativeCheckEvidence(BaseModel):
    evidence_id: str
    evidence_type: Literal["NEGATIVE_CHECK_EVIDENCE"] = "NEGATIVE_CHECK_EVIDENCE"
    related_expected_check: str = ""
    reason: str = ""
    file: str = ""
    function: str = ""
    line: Union[int, str] = ""
    confidence: float = 0.0


class MatchingResult(BaseModel):
    expected_check: str
    matching_status: MatchingStatus
    matched_observed_check: Optional[str] = None
    check_strength: Optional[CheckStrength] = None
    basis: List[str] = Field(default_factory=list)
    confidence: float = 0.0
    limitations: List[str] = Field(default_factory=list)


class MissingCheckSummary(BaseModel):
    satisfied_checks: List[str] = Field(default_factory=list)
    partially_satisfied_checks: List[str] = Field(default_factory=list)
    weakly_related_checks: List[str] = Field(default_factory=list)
    missing_check_candidates: List[str] = Field(default_factory=list)
    review_required_checks: List[str] = Field(default_factory=list)


class ExpectedCheckMatching(BaseModel):
    expected_check_matching_id: str
    candidate_id: str
    action: str
    field: str
    field_semantic: str = ""
    expected_checks: List[str] = Field(default_factory=list)
    observed_check_references: List[str] = Field(default_factory=list)
    matching_results: List[MatchingResult] = Field(default_factory=list)
    missing_check_summary: MissingCheckSummary = Field(default_factory=MissingCheckSummary)


class MissingCheckItem(BaseModel):
    check_id: str
    basis: str = ""
    confidence: float = 0.0
    reason: str = ""


class WeakCheckItem(BaseModel):
    check_id: str
    related_expected_check: Optional[str] = None
    reason: str = ""


class MissingCheckCandidateSet(BaseModel):
    missing_check_candidate_id: str
    candidate_id: str
    action: str
    field: str
    missing_check_candidates: List[MissingCheckItem] = Field(default_factory=list)
    weak_or_partial_check_candidates: List[WeakCheckItem] = Field(default_factory=list)
    review_required_missing_check_candidates: List[MissingCheckItem] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)


class OcppContext(BaseModel):
    ocpp_version: str = ""
    action: str = ""
    field: str = ""
    field_semantic: str = ""
    trust_level: str = ""


class CodeEvidence(BaseModel):
    source: SourceRef
    flow: List[FlowStep] = Field(default_factory=list)
    sink: SinkInfo


class CheckEvidence(BaseModel):
    expected_checks: List[str] = Field(default_factory=list)
    observed_checks: List[ObservedCheck] = Field(default_factory=list)
    missing_check_candidates: List[MissingCheckItem] = Field(default_factory=list)


class PrimaryLocation(BaseModel):
    file: str = ""
    line: Union[int, str] = ""
    evidence: str = ""


class Traceability(BaseModel):
    files: List[str] = Field(default_factory=list)
    functions: List[str] = Field(default_factory=list)
    primary_locations: List[PrimaryLocation] = Field(default_factory=list)


class ConfidenceBreakdown(BaseModel):
    handler_mapping: float = 0.0
    field_binding: float = 0.0
    semantic_binding: float = 0.0
    source_sink_flow: float = 0.0
    sink_mapping: float = 0.0
    check_detection: float = 0.0
    traceability: float = 0.0
    overall_static_confidence: float = 0.0


class SecurityInterpretation(BaseModel):
    summary: str = ""
    root_cause_candidates: List[str] = Field(default_factory=list)
    related_cwe: List[str] = Field(default_factory=list)


class EvidencePackage(BaseModel):
    evidence_id: str
    candidate_type: Literal["OCPP_NATIVE_EVIDENCE_PACKAGE"] = "OCPP_NATIVE_EVIDENCE_PACKAGE"
    language: str = "c"
    component_type: str = ""
    ocpp_context: OcppContext
    code_evidence: CodeEvidence
    check_evidence: CheckEvidence
    traceability: Traceability = Field(default_factory=Traceability)
    security_interpretation: SecurityInterpretation = Field(default_factory=SecurityInterpretation)
    root_cause_candidates: List[str] = Field(default_factory=list)
    related_cwe: List[str] = Field(default_factory=list)
    confidence: ConfidenceBreakdown = Field(default_factory=ConfidenceBreakdown)
    static_confidence: float = 0.0
    limitations: List[str] = Field(default_factory=list)


class CandidateFragment(BaseModel):
    candidate_id: str
    candidate_type: Literal["OCPP_NATIVE_CANDIDATE_HVVD_FRAGMENT"] = "OCPP_NATIVE_CANDIDATE_HVVD_FRAGMENT"
    language: str = "c"
    component_type: str = ""
    ocpp_context: OcppContext
    code_evidence: CodeEvidence
    expected_checks: List[str] = Field(default_factory=list)
    observed_checks: List[ObservedCheck] = Field(default_factory=list)
    missing_check_candidates: List[MissingCheckItem] = Field(default_factory=list)
    root_cause_candidates: List[str] = Field(default_factory=list)
    related_cwe: List[str] = Field(default_factory=list)
    static_confidence: float = 0.0
    lifecycle_state_hint: LifecycleStateHint = "STATIC_SUSPECT_HVVD"
    limitations: List[str] = Field(default_factory=list)


class FlowCandidate(BaseModel):
    candidate_id: str
    language: str = "c"
    component_type: str = ""
    ocpp_version: str = ""
    action: str
    field: str
    field_semantic: str = ""
    source: SourceRef
    flow: List[FlowStep] = Field(default_factory=list)
    sink: SinkInfo
    observed_checks: List[str] = Field(default_factory=list)
    expected_checks: List[str] = Field(default_factory=list)
    missing_check_candidates: List[str] = Field(default_factory=list)
    static_confidence: float = 0.0
    limitations: List[str] = Field(default_factory=list)


class F2AResult(BaseModel):
    source_cpg: str = ""
    handler_maps: List[HandlerMap] = Field(default_factory=list)
    handler_resolutions: List[HandlerResolution] = Field(default_factory=list)
    field_bindings: List[FieldBinding] = Field(default_factory=list)
    flow_candidates: List[FlowCandidate] = Field(default_factory=list)
    sink_mappings: List[SinkMapping] = Field(default_factory=list)
    expected_check_matchings: List[ExpectedCheckMatching] = Field(default_factory=list)
    missing_check_candidate_sets: List[MissingCheckCandidateSet] = Field(default_factory=list)
    evidence_packages: List[EvidencePackage] = Field(default_factory=list)
    candidate_fragments: List[CandidateFragment] = Field(default_factory=list)
    limitations: List[str] = Field(default_factory=list)
