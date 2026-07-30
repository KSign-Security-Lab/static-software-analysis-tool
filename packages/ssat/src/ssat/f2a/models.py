"""Data models for the F2-A OCPP-native evidence extraction pipeline.

Field names and enums follow the F2-A concept design
(``docs/v2/refs/V4_2 1 F2-A_개념상세 설계 …a1a85c.md``) and the implementation
deck (``docs/v2/f2a_deck_v7_implementation.html``).

The overarching invariant of F2-A: it does **not** confirm vulnerabilities.
Every artifact is a *candidate* backed by file/function/line evidence, a
connection-quality confidence, and explicit limitations, handed off to F6.
"""

from __future__ import annotations

from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Enums (verbatim from the concept design)
# ---------------------------------------------------------------------------

# §10.2 Dangerous Sink Domain Profile
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

# §11.6 observed-check strength
CheckStrength = Literal["STRONG", "PARTIAL", "WEAK", "UNKNOWN", "CONFLICTED"]

# §12.4 expected↔observed matching status
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

# §16.4 F2-A only ever emits a static-suspect hint (never CONFIRMED/DISMISSED)
LifecycleStateHint = Literal["STATIC_SUSPECT_HVVD", "REVIEW_READY_HVVD"]


# ---------------------------------------------------------------------------
# Shared building blocks
# ---------------------------------------------------------------------------


class CodeLocation(BaseModel):
    """A file/function/line anchor. Every piece of evidence is traceable."""

    file: str = ""
    function: str = ""
    line: Union[int, str] = ""


class MappingEvidence(BaseModel):
    """Evidence backing a handler mapping (``DISPATCH_STRING_MATCH`` / ``HANDLER_CALL``)."""

    type: str
    value: str = ""
    file: str = ""
    line: Union[int, str] = ""


# ---------------------------------------------------------------------------
# F2-A2 · Handler mapping
# ---------------------------------------------------------------------------


class HandlerRef(CodeLocation):
    language: str = "c"


class HandlerMap(BaseModel):
    """F2-A2 output — which function handles an OCPP action.

    Back-compat: populated only for RESOLVED actions. The authoritative
    per-action diagnostic (including AMBIGUOUS / UNRESOLVED) is
    ``F2AResult.handler_resolutions``.

    CONFIDENCE — the two values are NOT interchangeable:

    * ``HandlerMap.confidence`` is the *selected evidence weight* — the raw prior
      of the single strongest piece of evidence that backs the mapping (e.g. 0.90
      for a string dispatch). It is a backward-compatibility value with the
      historical meaning; it is NOT the aggregated resolution score.
    * ``HandlerResolution.candidates[*].confidence`` (see below) is the
      authoritative Phase-2 *aggregated* score (per-evidence scoring, provenance
      grouping, noisy-OR, caps). Downstream consumers that want the resolution
      confidence must read that field, not this one.

    Longer term ``HandlerMap.confidence`` should be deprecated or renamed to
    ``selected_evidence_weight`` to remove the ambiguity.
    """

    handler_map_id: str
    action: str
    handler: HandlerRef
    mapping_evidence: List[MappingEvidence] = Field(default_factory=list)
    confidence: float = 0.0  # selected evidence weight (back-compat); NOT the aggregated score


# --- Public handler-resolution view (serializable projection of the internal
#     SelectionResult; carries no CPG node references) -----------------------


class UnresolvedDispatchSite(BaseModel):
    file: str = ""
    line: Union[int, str] = ""
    code: str = ""


class ActionIdentifierView(BaseModel):
    """The action-id observation(s) a piece of evidence matched on."""

    protocol_string: Optional[str] = None
    symbol: Optional[str] = None
    numeric_id: Optional[int] = None
    normalized_name: Optional[str] = None
    raw_expression: Optional[str] = None
    resolved_value: Optional[Union[int, str]] = None


class EvidenceRecord(BaseModel):
    """One line of the resolution trail (a CPG anchor with its code)."""

    type: str  # DISPATCH_*, HANDLER_REF, ACTION_STORE, SLOT, CHAIN_CALL, CHAIN_STORE, ...
    value: str = ""  # the original code / value at that site
    file: str = ""
    line: Union[int, str] = ""


class HandlerResolutionEvidence(BaseModel):
    """A single auditable evidence record behind a candidate — the "how it was
    resolved" detail: kind, matched identifier, provenance, scores, and the trail
    of CPG sites (paired assignments / registrar chain)."""

    kind: str
    extractor: str = ""
    match_strength: str = ""  # EXACT_IDENTIFIER | RESOLVED_VALUE | NORMALIZED_NAME | HEURISTIC_SUBSTRING | NONE
    action_id_consistency: str = "PARTIAL"
    provenance_group: str = ""
    weight: float = 0.0
    score: float = 0.0  # post-penalty score used by the calculus
    score_pre_penalty: float = 0.0  # W*M before any identifier-consistency penalty
    action_id: ActionIdentifierView = Field(default_factory=ActionIdentifierView)
    dispatch_site: Optional[UnresolvedDispatchSite] = None
    records: List[EvidenceRecord] = Field(default_factory=list)


class HandlerResolutionCandidate(BaseModel):
    """One competing handler candidate, resolved to source coordinates, with the
    underlying evidence trail so the mapping is auditable."""

    function: str = ""
    file: str = ""
    line: Union[int, str] = ""
    confidence: float = 0.0  # authoritative Phase-2 aggregated score (NOT HandlerMap.confidence)
    evidence_kinds: List[str] = Field(default_factory=list)
    action_id_consistency: str = "PARTIAL"  # CONSISTENT | CONFLICTING | PARTIAL
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
    """Authoritative per-action resolution outcome (one per requested action).

    ``chosen`` is set *iff* ``status == 'RESOLVED'`` and is taken directly from
    the selector — assembly never re-derives a winner.

    ``candidates`` are in **selection order**: the selected candidate (when
    present) is always first, and the remainder is ordered by the selection
    policy (its post-policy confidence score) with a documented tie-break of
    (function, file, line). This tracks the selector rather than raw scoring, so
    it stays correct if a future policy selects a non-max-confidence candidate.

    ``conflict`` is present whenever more than one callback competed;
    ``unresolved`` when nothing bound.
    """

    action: str
    status: str  # RESOLVED | AMBIGUOUS | UNRESOLVED
    chosen: Optional[HandlerRef] = None
    candidates: List[HandlerResolutionCandidate] = Field(default_factory=list)
    conflict: Optional[ConflictReportView] = None
    unresolved: Optional[UnresolvedReportView] = None


# ---------------------------------------------------------------------------
# F2-A3 · Payload field source extraction
# ---------------------------------------------------------------------------


class BindingEvidence(BaseModel):
    type: str  # e.g. STRUCT_FIELD_ASSIGNMENT
    expression: str = ""


class FieldBindingDetail(BaseModel):
    source_type: str = "OCPP_PAYLOAD_FIELD"
    source_expression: str = ""
    bound_variable: str = ""
    file: str = ""
    function: str = ""
    line: Union[int, str] = ""


class FieldBinding(BaseModel):
    """F2-A3 output — the payload field bound to a concrete code variable."""

    field_binding_id: str
    action: str
    field: str
    field_semantic: str = ""
    binding: FieldBindingDetail
    binding_evidence: List[BindingEvidence] = Field(default_factory=list)
    confidence: float = 0.0


# ---------------------------------------------------------------------------
# F2-A4 · Semantic binding (from the F1 knowledge base)
# ---------------------------------------------------------------------------


class SemanticBinding(BaseModel):
    """F2-A4 output — KB meaning attached to the field."""

    field_semantic: str = ""
    trust_level: str = ""
    expected_checks: List[str] = Field(default_factory=list)
    dangerous_sink_domains: List[str] = Field(default_factory=list)
    related_cwe: List[str] = Field(default_factory=list)
    validation_requirement: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# F2-A5 · Source→sink flow
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# F2-A6 · Dangerous sink mapping
# ---------------------------------------------------------------------------


class SinkMapping(BaseModel):
    """F2-A6 output — the reached dangerous call, mapped to a domain + CWE."""

    sink_mapping_id: str
    sink: CodeLocation
    api: str = ""
    sink_domain: str = ""
    related_cwe: List[str] = Field(default_factory=list)
    severity_hint: str = ""
    mapping_evidence: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# F2-A7 · Observed check detection
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# F2-A8 · Expected check matching
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# F2-A9 · Missing check candidate
# ---------------------------------------------------------------------------


class MissingCheckItem(BaseModel):
    check_id: str
    basis: str = ""  # UNVERIFIED / WEAKLY_RELATED / NEGATIVE_EVIDENCE_FOUND
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


# ---------------------------------------------------------------------------
# F2-A10/A11 · Evidence package (the primary F6 hand-off)
# ---------------------------------------------------------------------------


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
    """F2-A10 output — the OCPP-native evidence package."""

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
    """F2-A15 output — the ``OCPP_NATIVE_CANDIDATE_HVVD_FRAGMENT`` handed to F6."""

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
    """F2-A5 output row (``ocpp_flow_candidates.jsonl``)."""

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
    """The full bundle produced for one CPG (all artifacts of one run)."""

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
