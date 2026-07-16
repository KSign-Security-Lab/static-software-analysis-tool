"""Adversarial tests for the public `F2AResult.handler_resolutions` output.

These exercise the SelectionResult -> HandlerResolution assembly on real fixture
CPGs under the current cascade policy (no corroboration). They lock down the six
details agreed for this increment: one entry per action, deterministic ordering,
`chosen` only when RESOLVED, structured unresolved reasons, all-registration
emission, and competitors retained with a conflict report.
"""

import json
from pathlib import Path

import pytest

from ssat.f2a import run_f2a_file
from ssat.f2a.graph import CPGModel
from ssat.f2a.pipeline import F2AAnalyzer
from ssat.f2a.resolution import ResolutionStatus

FX = Path(__file__).parent / "fixtures" / "f2a" / "cpg"
A = FX / "data_transfer_reg_vs_switch.c.json"
B = FX / "scp_dup_registration.c.json"
C = FX / "scp_numeric_vs_name.c.json"
D = FX / "scp_ambiguous_two_registrations.c.json"


def _need(p):
    if not p.exists():
        pytest.skip(f"fixture CPG not present: {p}")


def _res(result, action):
    return next(h for h in result.handler_resolutions if h.action == action)


# --- detail 6: registration->foo vs switch->bar -------------------------------


def test_competing_registration_vs_switch_retains_loser_and_conflict():
    _need(A)
    r = run_f2a_file(A)
    dt = _res(r, "DataTransfer")

    assert dt.status == "RESOLVED"
    assert dt.chosen is not None and dt.chosen.function == "bar"       # switch wins
    # chosen is first; the registration loser `foo` is retained as a ranked candidate
    assert dt.candidates[0].function == "bar"
    assert {c.function for c in dt.candidates} == {"bar", "foo"}
    # conflict is exposed with both competitors and the margin. Under the
    # corroborate policy (default) DataTransfer has no KB symbol/numeric, so both
    # matches are weak-basis: enum NORMALIZED 0.85*0.85=0.7225, registration
    # HEURISTIC 0.80*0.70=0.56 -> margin 0.1625.
    assert dt.conflict is not None
    assert {c.function for c in dt.conflict.competing} == {"bar", "foo"}
    assert dt.conflict.margin == round(0.7225 - 0.56, 6)


# --- detail 1: exactly one entry per requested action -------------------------


def test_one_resolution_entry_per_requested_action():
    _need(A)
    r = run_f2a_file(A)
    actions = [h.action for h in r.handler_resolutions]
    # one entry per KB action, no duplicates, including unresolved ones
    assert actions == sorted(set(actions), key=actions.index)
    assert set(actions) == {
        "UpdateFirmware", "DataTransfer", "SetChargingProfile", "RemoteStartTransaction",
    }
    statuses = {h.action: h.status for h in r.handler_resolutions}
    assert statuses["DataTransfer"] == "RESOLVED"
    assert statuses["UpdateFirmware"] == "UNRESOLVED"


# --- detail 3: chosen set iff RESOLVED; unresolved carries a structured reason -


def test_chosen_only_when_resolved_and_unresolved_is_structured():
    _need(A)
    r = run_f2a_file(A)
    uf = _res(r, "UpdateFirmware")
    assert uf.status == "UNRESOLVED"
    assert uf.chosen is None
    assert uf.unresolved is not None
    assert uf.unresolved.reason  # a non-empty reason string
    assert uf.candidates == []


# --- back-compat: handler_maps still populated, resolved-only -----------------


def test_handler_maps_backcompat_resolved_only():
    _need(A)
    r = run_f2a_file(A)
    mapped = {h.action: h.handler.function for h in r.handler_maps}
    assert mapped == {"DataTransfer": "bar"}  # only the resolved action


def test_chosen_is_always_first_candidate_invariant():
    """Selection-order invariant: for a RESOLVED action, chosen is candidates[0]
    (not merely the max-confidence entry, though they coincide under cascade)."""
    _need(A)
    r = run_f2a_file(A)
    for res in r.handler_resolutions:
        if res.status == "RESOLVED":
            assert res.chosen is not None
            assert res.candidates[0].function == res.chosen.function


def test_result_is_json_serializable():
    _need(A)
    r = run_f2a_file(A)
    json.dumps(r.model_dump(), default=str)  # no CPG node refs leak into the public model


# --- detail 5: duplicate registrations -> one candidate, multiple evidence ----


def test_duplicate_registrations_form_one_candidate_multi_evidence():
    _need(B)
    m = CPGModel(json.loads(B.read_text()))
    sel = F2AAnalyzer(m)._resolve_handler("SetChargingProfile")
    assert sel.status is ResolutionStatus.RESOLVED
    assert len(sel.candidates) == 1                       # same callback -> one candidate
    assert len(sel.candidates[0].evidence) == 2           # two registrations -> two evidences
    assert sel.conflict is None                           # not competing


# --- match-strength distinction: exact numeric registration beats weak name ---


def test_ambiguous_two_registrations_no_binding():
    """Two rows for the same action id (41) pointing to different callbacks: two
    candidates at 0.80, margin 0 < AMBIGUITY_MARGIN -> AMBIGUOUS, no binding, both
    retained, conflict exposed, and no HandlerMap emitted."""
    _need(D)
    r = run_f2a_file(D)
    scp = _res(r, "SetChargingProfile")
    assert scp.status == "AMBIGUOUS"
    assert scp.chosen is None
    assert {c.function for c in scp.candidates} == {"handler_a", "handler_b"}
    assert scp.conflict is not None
    assert scp.conflict.margin == 0.0
    # AMBIGUOUS must not leak into the back-compat resolved-only projection
    assert "SetChargingProfile" not in {h.action for h in r.handler_maps}


def test_exact_numeric_registration_beats_weak_name():
    _need(C)
    r = run_f2a_file(C)
    scp = _res(r, "SetChargingProfile")
    assert scp.status == "RESOLVED"
    assert scp.chosen.function == "store_profile"         # registration 0.80 > name 0.70
    by_fn = {c.function: c for c in scp.candidates}
    assert "handle_set_charging_profile" in by_fn         # weak name retained as competitor
    assert by_fn["store_profile"].evidence_kinds == ["REGISTRATION_INIT"]
    assert by_fn["handle_set_charging_profile"].evidence_kinds == ["NAME_MATCH"]
    assert scp.conflict is not None
    assert {c.function for c in scp.conflict.competing} == {
        "store_profile", "handle_set_charging_profile",
    }
