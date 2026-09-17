from pathlib import Path

import pytest

from ssat.f2a import run_f2a_file

FIXTURES = Path(__file__).parent / "fixtures" / "f2a" / "cpg"
FIXTURE_CPG = FIXTURES / "update_firmware.c.json"
FIXTURE_CHECKED_CPG = FIXTURES / "update_firmware_checked.c.json"
FIXTURE_DT_CPG = FIXTURES / "data_transfer.c.json"
FIXTURE_DT_ENUM_CPG = FIXTURES / "data_transfer_enum.c.json"
FIXTURE_SCP_CPG = FIXTURES / "set_charging_profile.c.json"
FIXTURE_SCP_CHECKED_CPG = FIXTURES / "set_charging_profile_checked.c.json"
FIXTURE_SCP_TABLE_CPG = FIXTURES / "set_charging_profile_table.c.json"


@pytest.fixture(scope="module")
def result():
    if not FIXTURE_CPG.exists():
        pytest.skip(f"fixture CPG not present: {FIXTURE_CPG}")
    return run_f2a_file(FIXTURE_CPG)


@pytest.fixture(scope="module")
def checked_result():
    if not FIXTURE_CHECKED_CPG.exists():
        pytest.skip(f"fixture CPG not present: {FIXTURE_CHECKED_CPG}")
    return run_f2a_file(FIXTURE_CHECKED_CPG)


@pytest.fixture(scope="module")
def data_transfer_result():
    if not FIXTURE_DT_CPG.exists():
        pytest.skip(f"fixture CPG not present: {FIXTURE_DT_CPG}")
    return run_f2a_file(FIXTURE_DT_CPG)


def test_handler_discovered(result):
    assert len(result.handler_maps) == 1
    hm = result.handler_maps[0]
    assert hm.action == "UpdateFirmware"
    assert hm.handler.function == "handle_update_firmware"
    assert {e.type for e in hm.mapping_evidence} == {
        "DISPATCH_STRING_MATCH",
        "HANDLER_CALL",
    }


def test_source_bound_to_variable(result):
    assert len(result.field_bindings) == 1
    fb = result.field_bindings[0]
    assert fb.field == "location"
    assert fb.field_semantic == "firmware_download_url"
    assert fb.binding.bound_variable == "firmware_url"


def test_flow_reaches_command_execution_sink(result):
    assert len(result.evidence_packages) == 1
    pkg = result.evidence_packages[0]
    sink = pkg.code_evidence.sink
    assert sink.api == "system"
    assert sink.sink_domain == "COMMAND_EXECUTION"
    functions = {step.function for step in pkg.code_evidence.flow}
    assert {"handle_update_firmware", "download_firmware"} <= functions


def test_observed_null_check_is_weak(result):
    pkg = result.evidence_packages[0]
    observed = pkg.check_evidence.observed_checks
    null_checks = [o for o in observed if o.check_type == "NULL_CHECK"]
    assert null_checks, "expected the null check to be detected"
    assert null_checks[0].check_strength == "WEAK"


def test_missing_and_negative_checks(result):
    pkg = result.evidence_packages[0]
    by_id = {m.check_id: m.basis for m in pkg.check_evidence.missing_check_candidates}
    for check in ("URL_SCHEME_VALIDATION", "HOST_ALLOWLIST", "SIGNATURE_VERIFICATION"):
        assert by_id.get(check) == "UNVERIFIED"
    assert by_id.get("SAFE_DOWNLOAD_API_NO_SHELL") == "NEGATIVE_EVIDENCE_FOUND"


@pytest.fixture(scope="module")
def data_transfer_enum_result():
    if not FIXTURE_DT_ENUM_CPG.exists():
        pytest.skip(f"fixture CPG not present: {FIXTURE_DT_ENUM_CPG}")
    return run_f2a_file(FIXTURE_DT_ENUM_CPG)


def test_data_transfer_reaches_sql_sink(data_transfer_result):
    assert len(data_transfer_result.evidence_packages) == 1
    p = data_transfer_result.evidence_packages[0]
    assert p.ocpp_context.action == "DataTransfer"
    assert p.ocpp_context.field == "data"
    assert p.ocpp_context.field_semantic == "vendor_controlled_payload"
    assert p.code_evidence.sink.api == "sqlite3_exec"
    assert p.code_evidence.sink.sink_domain == "database_query_execution"


def test_data_transfer_missing_and_negative_checks(data_transfer_result):
    p = data_transfer_result.evidence_packages[0]
    by_id = {m.check_id: m.basis for m in p.check_evidence.missing_check_candidates}
    assert by_id.get("DT_DATA_SCHEMA_VALIDATION") == "UNVERIFIED"
    assert by_id.get("DT_DATA_LENGTH_LIMIT") == "UNVERIFIED"
    assert by_id.get("SQL_PARAMETERIZATION") == "NEGATIVE_EVIDENCE_FOUND"
    assert "CWE-89" in p.related_cwe


def test_related_cwe_and_lifecycle(result):
    pkg = result.evidence_packages[0]
    assert "CWE-78" in pkg.related_cwe
    assert result.candidate_fragments[0].lifecycle_state_hint == "STATIC_SUSPECT_HVVD"


def test_confidence_is_connection_quality(result):
    pkg = result.evidence_packages[0]
    assert 0.6 <= pkg.static_confidence <= 0.95
    assert pkg.confidence.sink_mapping == 1.0


def test_structural_classifier_detects_scheme_and_signature(checked_result):
    pkg = checked_result.evidence_packages[0]
    by_type = {o.check_type: o for o in pkg.check_evidence.observed_checks}
    assert by_type["URL_SCHEME_CHECK"].check_strength == "STRONG"
    assert by_type["URL_SCHEME_CHECK"].matched_expected_check == "URL_SCHEME_VALIDATION"
    assert by_type["SIGNATURE_VERIFICATION"].check_strength == "STRONG"
    assert "NULL_CHECK" in by_type


def test_structural_classifier_no_duplicate_checks(checked_result):
    pkg = checked_result.evidence_packages[0]
    types = [o.check_type for o in pkg.check_evidence.observed_checks]
    assert len(types) == len(set(types)), f"duplicate observed checks: {types}"


def test_satisfied_checks_leave_only_host_and_shell_missing(checked_result):
    matching = checked_result.expected_check_matchings[0]
    status = {r.expected_check: r.matching_status for r in matching.matching_results}
    assert status["URL_SCHEME_VALIDATION"] == "SATISFIED"
    assert status["SIGNATURE_VERIFICATION"] == "SATISFIED"
    assert status["HOST_ALLOWLIST"] == "UNVERIFIED"
    assert status["SAFE_DOWNLOAD_API_NO_SHELL"] == "NEGATIVE_EVIDENCE_FOUND"


def test_enum_dispatch_handler_discovered(data_transfer_enum_result):
    assert len(data_transfer_enum_result.handler_maps) == 1
    hm = data_transfer_enum_result.handler_maps[0]
    assert hm.action == "DataTransfer"
    assert hm.handler.function == "handle_data_transfer"
    assert {e.type for e in hm.mapping_evidence} == {
        "DISPATCH_ENUM_CASE",
        "HANDLER_CALL",
    }


def test_enum_dispatch_flow_reaches_sql_sink(data_transfer_enum_result):
    assert len(data_transfer_enum_result.evidence_packages) == 1
    p = data_transfer_enum_result.evidence_packages[0]
    assert p.ocpp_context.action == "DataTransfer"
    assert p.ocpp_context.field == "data"
    assert p.code_evidence.sink.api == "sqlite3_exec"
    assert p.code_evidence.sink.sink_domain == "database_query_execution"
    functions = {step.function for step in p.code_evidence.flow}
    assert {"handle_data_transfer", "insert_diagnostic_record"} <= functions
    assert "CWE-89" in p.related_cwe


@pytest.fixture(scope="module")
def scp_result():
    if not FIXTURE_SCP_CPG.exists():
        pytest.skip(f"fixture CPG not present: {FIXTURE_SCP_CPG}")
    return run_f2a_file(FIXTURE_SCP_CPG)


@pytest.fixture(scope="module")
def scp_checked_result():
    if not FIXTURE_SCP_CHECKED_CPG.exists():
        pytest.skip(f"fixture CPG not present: {FIXTURE_SCP_CHECKED_CPG}")
    return run_f2a_file(FIXTURE_SCP_CHECKED_CPG)


def _pkg_for_field(result, suffix):
    for p in result.evidence_packages:
        if p.ocpp_context.field.endswith(suffix):
            return p
    raise AssertionError(f"no evidence package for field *{suffix}")


def test_scp_flow_reaches_memcpy_sink(scp_result):
    hm = scp_result.handler_maps[0]
    assert hm.action == "SetChargingProfile"
    assert hm.handler.function == "handle_set_charging_profile"
    assert {e.type for e in hm.mapping_evidence} == {"HANDLER_NAME_PATTERN"}

    fields = {p.ocpp_context.field for p in scp_result.evidence_packages}
    assert fields == {
        "csChargingProfiles.chargingSchedule",
        "csChargingProfiles.chargingSchedule.length",
    }
    for p in scp_result.evidence_packages:
        assert p.ocpp_context.action == "SetChargingProfile"
        assert p.code_evidence.sink.api == "memcpy"
        assert p.code_evidence.sink.sink_domain == "MEMORY_UNSAFE_OPERATION"
        assert "CWE-120" in p.related_cwe
    payload = _pkg_for_field(scp_result, "chargingSchedule")
    functions = {step.function for step in payload.code_evidence.flow}
    assert {"handle_set_charging_profile", "store_charging_profile"} <= functions


def test_scp_length_bound_missing_when_absent(scp_result):
    p = _pkg_for_field(scp_result, "chargingSchedule.length")
    by_id = {m.check_id: m.basis for m in p.check_evidence.missing_check_candidates}
    assert by_id.get("SCP_PROFILE_LENGTH_BOUND") == "UNVERIFIED"


def test_scp_length_bound_observed_structurally(scp_checked_result):
    p = _pkg_for_field(scp_checked_result, "chargingSchedule.length")
    by_type = {o.check_type: o for o in p.check_evidence.observed_checks}
    assert "LENGTH_BOUND_CHECK" in by_type
    assert by_type["LENGTH_BOUND_CHECK"].check_strength == "STRONG"
    assert by_type["LENGTH_BOUND_CHECK"].matched_expected_check == "SCP_PROFILE_LENGTH_BOUND"
    by_id = {m.check_id: m.basis for m in p.check_evidence.missing_check_candidates}
    assert "SCP_PROFILE_LENGTH_BOUND" not in by_id


@pytest.fixture(scope="module")
def scp_table_result():
    if not FIXTURE_SCP_TABLE_CPG.exists():
        pytest.skip(f"fixture CPG not present: {FIXTURE_SCP_TABLE_CPG}")
    return run_f2a_file(FIXTURE_SCP_TABLE_CPG)


def test_scp_table_handler_discovered_by_registration_entry(scp_table_result):
    hm = scp_table_result.handler_maps[0]
    assert hm.action == "SetChargingProfile"
    assert hm.handler.function == "process_configuration"
    assert {e.type for e in hm.mapping_evidence} == {"DISPATCH_HANDLER_TABLE", "HANDLER_REF"}


def test_scp_table_flow_reaches_memcpy_via_getter_return(scp_table_result):
    fields = {p.ocpp_context.field for p in scp_table_result.evidence_packages}
    assert fields == {
        "csChargingProfiles.chargingSchedule",
        "csChargingProfiles.chargingSchedule.length",
    }
    payload = _pkg_for_field(scp_table_result, "chargingSchedule")
    assert payload.code_evidence.sink.api == "memcpy"
    ops = [s.operation for s in payload.code_evidence.flow]
    assert any(o.startswith("return_value") for o in ops), ops
    functions = {s.function for s in payload.code_evidence.flow}
    assert {"resolve_schedule", "process_configuration", "copy_profile_bytes"} <= functions


def test_scp_table_guarded_bound_is_only_partial(scp_table_result):
    length = _pkg_for_field(scp_table_result, "chargingSchedule.length")
    by_type = {o.check_type: o for o in length.check_evidence.observed_checks}
    assert by_type["LENGTH_BOUND_CHECK"].check_strength == "PARTIAL"
    statuses = {
        r.matching_status
        for m in scp_table_result.expected_check_matchings
        for r in m.matching_results
        if r.expected_check == "SCP_PROFILE_LENGTH_BOUND"
    }
    assert "PARTIALLY_SATISFIED" in statuses
    assert "SATISFIED" not in statuses
