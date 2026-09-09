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


def test_action_identifier_numeric_conflict_is_kb_free():
    aid = ActionIdentifier(symbol="ACTION_X", resolved_value=15, numeric_id=41)
    assert aid.consistency() is ConsistencyState.CONFLICTING


def test_action_identifier_conflict_via_kb():
    kb = default_knowledge_base()
    aid = ActionIdentifier(symbol="ACTION_SET_CHARGING_PROFILE", normalized_name="DataTransfer")
    assert aid.consistency(kb) is ConsistencyState.CONFLICTING


def test_action_identifier_consistent_via_kb():
    kb = default_knowledge_base()
    aid = ActionIdentifier(symbol="ACTION_SET_CHARGING_PROFILE", numeric_id=41)
    assert aid.consistency(kb) is ConsistencyState.CONSISTENT


def test_action_identifier_partial_single_field():
    kb = default_knowledge_base()
    assert ActionIdentifier(numeric_id=41).consistency(kb) is ConsistencyState.PARTIAL
    assert ActionIdentifier(symbol="ACTION_X").consistency() is ConsistencyState.PARTIAL


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


def test_multiple_competing_candidates_cascade():
    enum_c = HandlerCandidate(callback=100, evidence=[_ev(ENUM_CASE, 100, 0.85)])
    name_c = HandlerCandidate(callback=200, evidence=[_ev(NAME_MATCH, 200, 0.70)])
    sel = select_cascade([name_c, enum_c])

    assert sel.status is ResolutionStatus.RESOLVED
    assert sel.chosen.callback == 100
    assert sel.conflict is not None
    assert {c["callback"] for c in sel.conflict.competing} == {100, 200}
    assert sel.conflict.margin == round(0.85 - 0.70, 6)


def test_equal_weight_tie_broken_by_kind_rank():
    reg = HandlerCandidate(callback=1, evidence=[_ev(REGISTRAR_CALL, 1, 0.70)])
    name = HandlerCandidate(callback=2, evidence=[_ev(NAME_MATCH, 2, 0.70)])
    sel = select_cascade([name, reg])
    assert sel.chosen.callback == 1


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


def test_match_strength_rank_is_explicit_and_strictly_ordered():
    order = [
        MatchStrength.EXACT_IDENTIFIER,
        MatchStrength.RESOLVED_VALUE,
        MatchStrength.NORMALIZED_NAME,
        MatchStrength.HEURISTIC_SUBSTRING,
        MatchStrength.NONE,
    ]
    ranks = [MATCH_STRENGTH_RANK[m] for m in order]
    assert ranks == sorted(ranks, reverse=True)
    assert len(set(ranks)) == len(order)
    assert set(MATCH_STRENGTH_RANK) == set(MatchStrength)


def test_dedupe_collapses_identical_keeps_strongest():
    weak = _cev(REGISTRATION_INIT, 1, MatchStrength.HEURISTIC_SUBSTRING, "g", 0.80, nodes=[10, 11], extractor="b")
    strong = _cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "g", 0.80, nodes=[11, 10], extractor="a")
    out = dedupe_evidence([weak, strong])
    assert len(out) == 1
    assert out[0].match_strength is MatchStrength.EXACT_IDENTIFIER
    other = _cev(NAME_MATCH, 1, MatchStrength.NORMALIZED_NAME, "token:X", 0.70, nodes=[10, 11])
    assert len(dedupe_evidence([strong, other])) == 2


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
    assert sel.chosen.confidence == round(1 - (1 - 0.85) * (1 - 0.80), 6)


def test_corroborate_same_group_takes_max_no_inflation():
    c = HandlerCandidate(
        1,
        [
            _cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "site:reg:7", 0.80),
            _cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "site:reg:7", 0.85),
        ],
    )
    sel = select_corroborate([c], kb=None)
    assert sel.chosen.confidence == 0.85


def test_corroborate_weak_only_cap():
    c = HandlerCandidate(
        1,
        [
            _cev(NAME_MATCH, 1, MatchStrength.NORMALIZED_NAME, "token:A", 0.70),
            _cev(NAME_MATCH, 1, MatchStrength.NORMALIZED_NAME, "token:B", 0.70),
            _cev(NAME_MATCH, 1, MatchStrength.NORMALIZED_NAME, "token:C", 0.70),
        ],
    )
    sel = select_corroborate([c], kb=None)
    assert sel.chosen.confidence == 0.85


def test_corroborate_conflicting_identifier_penalty_with_diagnostics():
    conflicted = ActionIdentifier(numeric_id=41, resolved_value=15)
    e = _cev(REGISTRATION_INIT, 1, MatchStrength.EXACT_IDENTIFIER, "site:reg:7", 0.80, aid=conflicted)
    sel = select_corroborate([HandlerCandidate(1, [e])], kb=None)
    assert e.score_pre_penalty == 0.80
    assert e.score == round(0.80 * 0.70 * 0.5, 6)
    assert sel.status is ResolutionStatus.UNRESOLVED
    assert sel.unresolved.reason is UnresolvedReason.LOW_CONFIDENCE


def test_corroborate_low_confidence_retains_candidates():
    e = _cev(NAME_MATCH, 1, MatchStrength.HEURISTIC_SUBSTRING, "token:X", 0.65)
    sel = select_corroborate([HandlerCandidate(1, [e])], kb=None)
    assert sel.status is ResolutionStatus.UNRESOLVED
    assert sel.chosen is None
    assert sel.unresolved.reason is UnresolvedReason.LOW_CONFIDENCE
    assert [c.callback for c in sel.candidates] == [1]


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
    cand = HandlerCandidate(
        callback=100,
        evidence=[_ev(ENUM_CASE, 100, 0.85), _ev(NAME_MATCH, 100, 0.70)],
    )
    sel = select_cascade([cand])
    assert sel.chosen.confidence == 0.85


def _resolve(fixture, action, selection="cascade"):
    m = CPGModel(json.loads((FX / fixture).read_text()))
    return F2AAnalyzer(m, selection=selection)._resolve_handler(action)


def test_integration_string_dispatch_evidence_cascade():
    if not (FX / "update_firmware.c.json").exists():
        import pytest

        pytest.skip("fixture CPG not present")
    sel = _resolve("update_firmware.c.json", "UpdateFirmware", selection="cascade")
    assert sel.status is ResolutionStatus.RESOLVED
    kinds = {e.kind for e in sel.chosen.evidence}
    assert STRING_DISPATCH in kinds
    assert sel.chosen.confidence == 0.9


def test_integration_enum_candidate_gathers_multiple_evidence_cascade():
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
    if not (FX / "data_transfer_enum.c.json").exists():
        import pytest

        pytest.skip("fixture CPG not present")
    sel = _resolve("data_transfer_enum.c.json", "DataTransfer", selection="corroborate")
    assert sel.status is ResolutionStatus.RESOLVED
    assert sel.chosen.confidence == 0.7225
