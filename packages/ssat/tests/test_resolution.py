"""Unit + light-integration tests for the handler-resolution model (F2-A step 1).

The pure tests (ActionIdentifier consistency, select_cascade) need no CPG. Two
integration tests load pre-generated fixture CPGs to confirm the extractors emit
evidence and cascade selection groups it, without changing behaviour.
"""

import json
from pathlib import Path

from ssat.f2a.graph import CPGModel
from ssat.f2a.kb import default_knowledge_base
from ssat.f2a.pipeline import F2AAnalyzer
from ssat.f2a.resolution import (
    ENUM_CASE,
    MATCH_STRENGTH_RANK,
    NAME_MATCH,
    REGISTRATION_INIT,
    REGISTRAR_CALL,
    STRING_DISPATCH,
    ActionIdentifier,
    ConsistencyState,
    HandlerCandidate,
    MatchStrength,
    ResolutionEvidence,
    ResolutionStatus,
    UnresolvedReason,
    dedupe_evidence,
    select_cascade,
    select_corroborate,
)

FX = Path(__file__).parent / "fixtures" / "f2a" / "cpg"


def _ev(kind, callback, weight, match=MatchStrength.EXACT_IDENTIFIER):
    return ResolutionEvidence(
        kind=kind,
        action_id=ActionIdentifier(),
        weight=weight,
        match_strength=match,
        callback=callback,
        score=weight,
    )


# --- Q1: internally conflicting ActionIdentifier ------------------------------


def test_action_identifier_numeric_conflict_is_kb_free():
    """A symbol resolving to 15 while the numeric literal is 41 must not collapse
    into one identity — it is CONFLICTING even without a KB."""
    aid = ActionIdentifier(symbol="ACTION_X", resolved_value=15, numeric_id=41)
    assert aid.consistency() is ConsistencyState.CONFLICTING


def test_action_identifier_conflict_via_kb():
    """Symbol maps to SetChargingProfile, normalized name maps to DataTransfer."""
    kb = default_knowledge_base()
    aid = ActionIdentifier(symbol="ACTION_SET_CHARGING_PROFILE", normalized_name="DataTransfer")
    assert aid.consistency(kb) is ConsistencyState.CONFLICTING


def test_action_identifier_consistent_via_kb():
    """Symbol and numeric id both denote SetChargingProfile."""
    kb = default_knowledge_base()
    aid = ActionIdentifier(symbol="ACTION_SET_CHARGING_PROFILE", numeric_id=41)
    assert aid.consistency(kb) is ConsistencyState.CONSISTENT


def test_action_identifier_partial_single_field():
    kb = default_knowledge_base()
    assert ActionIdentifier(numeric_id=41).consistency(kb) is ConsistencyState.PARTIAL
    assert ActionIdentifier(symbol="ACTION_X").consistency() is ConsistencyState.PARTIAL


# --- Q4 / selection: empty -> UNRESOLVED --------------------------------------


def test_select_empty_is_unresolved_no_evidence():
    sel = select_cascade([])
    assert sel.status is ResolutionStatus.UNRESOLVED
    assert sel.chosen is None
    assert sel.unresolved is not None
    assert sel.unresolved.reason is UnresolvedReason.NO_EVIDENCE


def test_select_single_candidate_resolves_without_conflict():
    cand = HandlerCandidate(callback=100, evidence=[_ev(ENUM_CASE, 100, 0.85)])
    sel = select_cascade([cand])
    assert sel.status is ResolutionStatus.RESOLVED
    assert sel.chosen.callback == 100
    assert sel.conflict is None
    assert sel.chosen.confidence == 0.85


# --- multiple competing candidates (cascade policy: resolve top, record conflict) ---


def test_multiple_competing_candidates_cascade():
    """Two candidates for different callbacks. Cascade resolves the higher-weight
    one but MUST record the competitor in a ConflictReport (status not downgraded
    in Phase 1)."""
    enum_c = HandlerCandidate(callback=100, evidence=[_ev(ENUM_CASE, 100, 0.85)])
    name_c = HandlerCandidate(callback=200, evidence=[_ev(NAME_MATCH, 200, 0.70)])
    sel = select_cascade([name_c, enum_c])  # unsorted input

    assert sel.status is ResolutionStatus.RESOLVED
    assert sel.chosen.callback == 100  # higher weight wins regardless of input order
    assert sel.conflict is not None
    assert {c["callback"] for c in sel.conflict.competing} == {100, 200}
    assert sel.conflict.margin == round(0.85 - 0.70, 6)


def test_equal_weight_tie_broken_by_kind_rank():
    """Same weight, different kind -> the higher-ranked kind wins deterministically."""
    reg = HandlerCandidate(callback=1, evidence=[_ev(REGISTRAR_CALL, 1, 0.70)])
    name = HandlerCandidate(callback=2, evidence=[_ev(NAME_MATCH, 2, 0.70)])
    sel = select_cascade([name, reg])
    assert sel.chosen.callback == 1  # REGISTRAR_CALL rank > NAME_MATCH rank


def _cev(kind, callback, ms, group, weight, aid=None, nodes=None, extractor="x", dispatch_site=None):
    return ResolutionEvidence(
        kind=kind,
        action_id=aid or ActionIdentifier(),
        weight=weight,
        match_strength=ms,
        callback=callback,
        dispatch_site=dispatch_site,
        nodes=nodes or [],
        provenance_group=group,
        extractor=extractor,
    )


# --- §1 exact deduplication + explicit MATCH_STRENGTH_RANK --------------------


def test_match_strength_rank_is_explicit_and_strictly_ordered():
    order = [
        MatchStrength.EXACT_IDENTIFIER,
        MatchStrength.RESOLVED_VALUE,
        MatchStrength.NORMALIZED_NAME,
        MatchStrength.HEURISTIC_SUBSTRING,
        MatchStrength.NONE,
    ]
    ranks = [MATCH_STRENGTH_RANK[m] for m in order]
    assert ranks == sorted(ranks, reverse=True)  # strictly descending
    assert len(set(ranks)) == len(order)  # total, no ties
    assert set(MATCH_STRENGTH_RANK) == set(MatchStrength)  # covers every member


def test_dedupe_collapses_identical_keeps_strongest():
    # same (kind, callback, dispatch_site, nodes) from two extractors, differing
    # only in match_strength -> one survivor, the stronger match.
    weak = _cev(REGISTRATION_INIT, 1, MatchStrength.HEURISTIC_SUBSTRING, "g", 0.80, nodes=[10, 11], extractor="b")
    strong = _cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "g", 0.80, nodes=[11, 10], extractor="a")
    out = dedupe_evidence([weak, strong])
    assert len(out) == 1
    assert out[0].match_strength is MatchStrength.EXACT_IDENTIFIER
    # different kind for same callback is NOT a duplicate
    other = _cev(NAME_MATCH, 1, MatchStrength.NORMALIZED_NAME, "token:X", 0.70, nodes=[10, 11])
    assert len(dedupe_evidence([strong, other])) == 2


# --- §3 aggregation: group-max, noisy-OR, caps --------------------------------


def test_corroborate_independent_groups_noisy_or():
    c = HandlerCandidate(
        1,
        [
            _cev(ENUM_CASE, 1, MatchStrength.EXACT_IDENTIFIER, "site:switch:9", 0.85),
            _cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "site:reg:7", 0.80),
        ],
    )
    sel = select_corroborate([c], kb=None)
    assert sel.status is ResolutionStatus.RESOLVED
    assert sel.chosen.confidence == round(1 - (1 - 0.85) * (1 - 0.80), 6)  # 0.97


def test_corroborate_same_group_takes_max_no_inflation():
    c = HandlerCandidate(
        1,
        [
            _cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "site:reg:7", 0.80),
            _cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "site:reg:7", 0.85),
        ],
    )
    sel = select_corroborate([c], kb=None)
    assert sel.chosen.confidence == 0.85  # max within one group, not 0.97


def test_corroborate_weak_only_cap():
    # three independent weak groups would noisy-OR to ~0.933; capped at 0.85.
    c = HandlerCandidate(
        1,
        [
            _cev(NAME_MATCH, 1, MatchStrength.NORMALIZED_NAME, "token:A", 0.70),
            _cev(NAME_MATCH, 1, MatchStrength.NORMALIZED_NAME, "token:B", 0.70),
            _cev(NAME_MATCH, 1, MatchStrength.NORMALIZED_NAME, "token:C", 0.70),
        ],
    )
    sel = select_corroborate([c], kb=None)
    assert sel.chosen.confidence == 0.85  # WEAK_ONLY_CAP


def test_corroborate_conflicting_identifier_penalty_with_diagnostics():
    conflicted = ActionIdentifier(numeric_id=41, resolved_value=15)  # KB-free CONFLICTING
    e = _cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "site:reg:7", 0.80, aid=conflicted)
    sel = select_corroborate([HandlerCandidate(1, [e])], kb=None)
    assert e.score_pre_penalty == 0.80  # W*M before penalty (diagnostic)
    assert e.score == round(0.80 * 0.70 * 0.5, 6)  # cap M at 0.70, then x0.5 -> 0.28
    # 0.28 < MIN_CONFIDENCE -> UNRESOLVED, but per-evidence, not forced ambiguity
    assert sel.status is ResolutionStatus.UNRESOLVED
    assert sel.unresolved.reason is UnresolvedReason.LOW_CONFIDENCE


# --- §4 status: low-confidence + ambiguity ------------------------------------


def test_corroborate_low_confidence_retains_candidates():
    e = _cev(NAME_MATCH, 1, MatchStrength.HEURISTIC_SUBSTRING, "token:X", 0.65)  # 0.455
    sel = select_corroborate([HandlerCandidate(1, [e])], kb=None)
    assert sel.status is ResolutionStatus.UNRESOLVED
    assert sel.chosen is None
    assert sel.unresolved.reason is UnresolvedReason.LOW_CONFIDENCE
    assert [c.callback for c in sel.candidates] == [1]  # retained for review


def test_corroborate_ambiguous_within_margin():
    a = HandlerCandidate(1, [_cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "site:reg:7", 0.80)])
    b = HandlerCandidate(2, [_cev(REGISTRATION_INIT, 2, MatchStrength.EXACT_IDENTIFIER, "site:reg:8", 0.80)])
    sel = select_corroborate([a, b], kb=None)
    assert sel.status is ResolutionStatus.AMBIGUOUS
    assert sel.chosen is None
    assert sel.conflict is not None
    assert {c["callback"] for c in sel.conflict.competing} == {1, 2}
    assert sel.conflict.margin == 0.0


def test_cascade_does_not_corroborate():
    """Two evidences for the SAME callback -> confidence is the MAX weight, not a
    noisy-OR combination (corroboration is a later, opt-in policy)."""
    cand = HandlerCandidate(
        callback=100,
        evidence=[_ev(ENUM_CASE, 100, 0.85), _ev(NAME_MATCH, 100, 0.70)],
    )
    sel = select_cascade([cand])
    assert sel.chosen.confidence == 0.85  # not 1 - (1-0.85)(1-0.70) = 0.955


# --- integration: extractors emit evidence, grouped into candidates -----------


def _resolve(fixture, action, selection="cascade"):
    m = CPGModel(json.loads((FX / fixture).read_text()))
    return F2AAnalyzer(m, selection=selection)._resolve_handler(action)


def test_integration_string_dispatch_evidence_cascade():
    """Cascade policy: confidence is the strongest kind's raw weight."""
    if not (FX / "update_firmware.c.json").exists():
        import pytest

        pytest.skip("fixture CPG not present")
    sel = _resolve("update_firmware.c.json", "UpdateFirmware", selection="cascade")
    assert sel.status is ResolutionStatus.RESOLVED
    kinds = {e.kind for e in sel.chosen.evidence}
    assert STRING_DISPATCH in kinds
    assert sel.chosen.confidence == 0.9


def test_integration_enum_candidate_gathers_multiple_evidence_cascade():
    """The enum fixture's handler name also matches the KB pattern, so ONE
    candidate carries BOTH ENUM_CASE and NAME_MATCH evidence — proving evidence
    grouping — while cascade confidence stays 0.85 (no corroboration)."""
    if not (FX / "data_transfer_enum.c.json").exists():
        import pytest

        pytest.skip("fixture CPG not present")
    sel = _resolve("data_transfer_enum.c.json", "DataTransfer", selection="cascade")
    assert sel.status is ResolutionStatus.RESOLVED
    kinds = {e.kind for e in sel.chosen.evidence}
    assert {ENUM_CASE, NAME_MATCH} <= kinds
    assert sel.chosen.confidence == 0.85
    assert sel.conflict is None


def test_integration_corroborate_shared_token_no_inflation():
    """Corroborate policy: ENUM_CASE + NAME_MATCH on DataTransfer both reduce to
    the same weak token group ("token:DataTransfer"), so they take the group MAX
    (0.85*0.85 = 0.7225), NOT a noisy-OR — a shared naming token must not inflate."""
    if not (FX / "data_transfer_enum.c.json").exists():
        import pytest

        pytest.skip("fixture CPG not present")
    sel = _resolve("data_transfer_enum.c.json", "DataTransfer", selection="corroborate")
    assert sel.status is ResolutionStatus.RESOLVED
    assert sel.chosen.confidence == 0.7225
