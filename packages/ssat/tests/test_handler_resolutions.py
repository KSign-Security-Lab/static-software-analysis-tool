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
E = FX / "scp_field_store.c.json"
R_DIRECT = FX / "scp_registrar_direct.c.json"
R_TWO = FX / "scp_registrar_two_level.c.json"
R_NOSTORE = FX / "scp_registrar_no_store.c.json"
R_SEARCH = FX / "scp_registrar_search_then_write.c.json"
DI = FX / "designated_init.c.json"
DI_ORDER = FX / "designated_init_order.c.json"
DI_NEG = FX / "designated_init_negatives.c.json"


def _need(p):
    if not p.exists():
        pytest.skip(f"fixture CPG not present: {p}")


def _res(result, action):
    return next(h for h in result.handler_resolutions if h.action == action)


def test_competing_registration_vs_switch_retains_loser_and_conflict():
    _need(A)
    r = run_f2a_file(A)
    dt = _res(r, "DataTransfer")

    assert dt.status == "RESOLVED"
    assert dt.chosen is not None and dt.chosen.function == "bar"
    assert dt.candidates[0].function == "bar"
    assert {c.function for c in dt.candidates} == {"bar", "foo"}
    assert dt.conflict is not None
    assert {c.function for c in dt.conflict.competing} == {"bar", "foo"}
    assert dt.conflict.margin == round(0.7225 - 0.56, 6)


def test_one_resolution_entry_per_requested_action():
    _need(A)
    r = run_f2a_file(A)
    actions = [h.action for h in r.handler_resolutions]
    assert actions == sorted(set(actions), key=actions.index)
    assert set(actions) == {
        "UpdateFirmware",
        "DataTransfer",
        "SetChargingProfile",
        "RemoteStartTransaction",
    }
    statuses = {h.action: h.status for h in r.handler_resolutions}
    assert statuses["DataTransfer"] == "RESOLVED"
    assert statuses["UpdateFirmware"] == "UNRESOLVED"


def test_chosen_only_when_resolved_and_unresolved_is_structured():
    _need(A)
    r = run_f2a_file(A)
    uf = _res(r, "UpdateFirmware")
    assert uf.status == "UNRESOLVED"
    assert uf.chosen is None
    assert uf.unresolved is not None
    assert uf.unresolved.reason
    assert uf.candidates == []


def test_handler_maps_backcompat_resolved_only():
    _need(A)
    r = run_f2a_file(A)
    mapped = {h.action: h.handler.function for h in r.handler_maps}
    assert mapped == {"DataTransfer": "bar"}


def test_chosen_is_always_first_candidate_invariant():
    _need(A)
    r = run_f2a_file(A)
    for res in r.handler_resolutions:
        if res.status == "RESOLVED":
            assert res.chosen is not None
            assert res.candidates[0].function == res.chosen.function


def test_result_is_json_serializable():
    _need(A)
    r = run_f2a_file(A)
    json.dumps(r.model_dump(), default=str)


def test_duplicate_registrations_form_one_candidate_multi_evidence():
    _need(B)
    m = CPGModel(json.loads(B.read_text()))
    sel = F2AAnalyzer(m)._resolve_handler("SetChargingProfile")
    assert sel.status is ResolutionStatus.RESOLVED
    assert len(sel.candidates) == 1
    assert len(sel.candidates[0].evidence) == 2
    assert sel.conflict is None


def test_ambiguous_two_registrations_no_binding():
    _need(D)
    r = run_f2a_file(D)
    scp = _res(r, "SetChargingProfile")
    assert scp.status == "AMBIGUOUS"
    assert scp.chosen is None
    assert {c.function for c in scp.candidates} == {"handler_a", "handler_b"}
    assert scp.conflict is not None
    assert scp.conflict.margin == 0.0
    assert "SetChargingProfile" not in {h.action for h in r.handler_maps}


def test_producer1_correlated_field_store():
    _need(E)
    r = run_f2a_file(E)
    scp = _res(r, "SetChargingProfile")
    assert scp.status == "RESOLVED"
    assert scp.chosen.function == "on_scp"
    assert scp.candidates[0].evidence_kinds == ["REGISTRATION_ASSIGN"]


def test_producer2_registrar_direct():
    _need(R_DIRECT)
    scp = _res(run_f2a_file(R_DIRECT), "SetChargingProfile")
    assert scp.status == "RESOLVED"
    assert scp.chosen.function == "on_scp"
    assert scp.candidates[0].evidence_kinds == ["REGISTRAR_CALL"]


def test_producer2_registrar_two_level():
    _need(R_TWO)
    scp = _res(run_f2a_file(R_TWO), "SetChargingProfile")
    assert scp.status == "RESOLVED"
    assert scp.chosen.function == "on_scp"
    assert scp.candidates[0].evidence_kinds == ["REGISTRAR_CALL"]


def test_producer2_registrar_store_not_reached_emits_no_evidence():
    _need(R_NOSTORE)
    scp = _res(run_f2a_file(R_NOSTORE), "SetChargingProfile")
    assert scp.status == "UNRESOLVED"
    assert scp.candidates == []
    assert scp.unresolved is not None
    assert scp.unresolved.reason == "REGISTRAR_STORE_NOT_REACHED"


def test_producer2_registrar_search_then_write_is_named_specifically():
    _need(R_SEARCH)
    scp = _res(run_f2a_file(R_SEARCH), "SetChargingProfile")
    assert scp.status == "UNRESOLVED"
    assert scp.candidates == []
    assert scp.unresolved is not None
    assert scp.unresolved.reason == "REGISTRAR_SEARCH_THEN_WRITE"


def test_designated_initializer_resolves_like_positional_aggregate():
    _need(DI)
    rs = _res(run_f2a_file(DI), "RemoteStartTransaction")
    assert rs.status == "RESOLVED"
    assert rs.chosen is not None and rs.chosen.function == "remote_handler"
    assert rs.candidates[0].evidence_kinds == ["REGISTRATION_INIT"]
    records = rs.candidates[0].evidence[0].records
    kinds = {r.type for r in records}
    assert {"DISPATCH_HANDLER_TABLE", "ACTION_STORE", "HANDLER_REF"} <= kinds
    table = next(r for r in records if r.type == "DISPATCH_HANDLER_TABLE")
    assert ".action = ACTION_REMOTE_START" in table.value and ".fn = remote_handler" in table.value


def test_designated_initializer_is_field_order_independent_and_multi_entry():
    _need(DI_ORDER)
    result = run_f2a_file(DI_ORDER)
    rs = _res(result, "RemoteStartTransaction")
    dt = _res(result, "DataTransfer")
    assert rs.status == "RESOLVED" and rs.chosen.function == "remote_handler"
    assert dt.status == "RESOLVED" and dt.chosen.function == "data_handler"
    assert rs.candidates[0].evidence_kinds == ["REGISTRATION_INIT"]
    assert dt.candidates[0].evidence_kinds == ["REGISTRATION_INIT"]


def test_designated_initializer_negatives_stay_unresolved():
    _need(DI_NEG)
    result = run_f2a_file(DI_NEG)
    assert all(h.status == "UNRESOLVED" for h in result.handler_resolutions)
    fns = {c.function for h in result.handler_resolutions for c in h.candidates}
    assert "lonely_handler" not in fns
    assert "log_sink" not in fns


def test_ambiguous_compat_limitation_names_competitors_not_not_found():
    _need(D)
    r = run_f2a_file(D)
    scp_lims = [x for x in r.limitations if "'SetChargingProfile'" in x]
    assert any("Multiple competing handlers" in x and "no handler selected" in x for x in scp_lims)
    assert not any("No handler found for action 'SetChargingProfile'" in x for x in scp_lims)


def test_exact_numeric_registration_beats_weak_name():
    _need(C)
    r = run_f2a_file(C)
    scp = _res(r, "SetChargingProfile")
    assert scp.status == "RESOLVED"
    assert scp.chosen.function == "store_profile"
    by_fn = {c.function: c for c in scp.candidates}
    assert "handle_set_charging_profile" in by_fn
    assert by_fn["store_profile"].evidence_kinds == ["REGISTRATION_INIT"]
    assert by_fn["handle_set_charging_profile"].evidence_kinds == ["NAME_MATCH"]
    assert scp.conflict is not None
    assert {c.function for c in scp.conflict.competing} == {
        "store_profile",
        "handle_set_charging_profile",
    }
