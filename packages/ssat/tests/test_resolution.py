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
    NAME_MATCH,
    REGISTRAR_CALL,
    STRING_DISPATCH,
    ActionIdentifier,
    ConsistencyState,
    HandlerCandidate,
    MatchStrength,
    ResolutionEvidence,
    ResolutionStatus,
    UnresolvedReason,
    select_cascade,
)

FX = Path(__file__).parent / "fixtures" / "f2a" / "cpg"


def _ev(kind, callback, weight, match=MatchStrength.EXACT_IDENTIFIER):
    return ResolutionEvidence(
        kind=kind, action_id=ActionIdentifier(), weight=weight,
        match_strength=match, callback=callback, score=weight,
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


def _resolve(fixture, action):
    m = CPGModel(json.loads((FX / fixture).read_text()))
    return F2AAnalyzer(m)._resolve_handler(action)


def test_integration_string_dispatch_evidence():
    if not (FX / "update_firmware.c.json").exists():
        import pytest
        pytest.skip("fixture CPG not present")
    sel = _resolve("update_firmware.c.json", "UpdateFirmware")
    assert sel.status is ResolutionStatus.RESOLVED
    kinds = {e.kind for e in sel.chosen.evidence}
    assert STRING_DISPATCH in kinds
    assert sel.chosen.confidence == 0.9  # cascade keeps the strongest kind's weight


def test_integration_enum_candidate_gathers_multiple_evidence():
    """The enum fixture's handler name also matches the KB pattern, so ONE
    candidate carries BOTH ENUM_CASE and NAME_MATCH evidence — proving evidence
    grouping — while cascade confidence stays 0.85 (no corroboration)."""
    if not (FX / "data_transfer_enum.c.json").exists():
        import pytest
        pytest.skip("fixture CPG not present")
    sel = _resolve("data_transfer_enum.c.json", "DataTransfer")
    assert sel.status is ResolutionStatus.RESOLVED
    kinds = {e.kind for e in sel.chosen.evidence}
    assert {ENUM_CASE, NAME_MATCH} <= kinds
    assert sel.chosen.confidence == 0.85
    assert sel.conflict is None
