"""End-to-end tests for the F2-A pipeline.

Runs F2-A over a pre-generated CPG of the deck's synthetic ``UpdateFirmware``
example (``fixtures/f2a/cpg/update_firmware.c.json``) and asserts it reproduces
the evidence package described in the implementation deck (slide 18) and the
concept design (Appendix C).
"""

from pathlib import Path

import pytest

from ssat.f2a import run_f2a_file

FIXTURES = Path(__file__).parent / "fixtures" / "f2a" / "cpg"
FIXTURE_CPG = FIXTURES / "update_firmware.c.json"
FIXTURE_CHECKED_CPG = FIXTURES / "update_firmware_checked.c.json"
FIXTURE_DT_CPG = FIXTURES / "data_transfer.c.json"


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
    # flow crosses from the handler into the download helper
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
    # scheme/host/signature cannot be statically verified here
    for check in ("URL_SCHEME_VALIDATION", "HOST_ALLOWLIST", "SIGNATURE_VERIFICATION"):
        assert by_id.get(check) == "UNVERIFIED"
    # using system() is negative evidence for the no-shell requirement
    assert by_id.get("SAFE_DOWNLOAD_API_NO_SHELL") == "NEGATIVE_EVIDENCE_FOUND"


# --- DataTransfer.data -> SQL sink (KB entry) --------------------------------


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
    # reaching the raw DB sink is negative evidence for parameterization
    assert by_id.get("SQL_PARAMETERIZATION") == "NEGATIVE_EVIDENCE_FOUND"
    assert "CWE-89" in p.related_cwe


def test_related_cwe_and_lifecycle(result):
    pkg = result.evidence_packages[0]
    assert "CWE-78" in pkg.related_cwe  # command injection
    assert result.candidate_fragments[0].lifecycle_state_hint == "STATIC_SUSPECT_HVVD"


def test_confidence_is_connection_quality(result):
    pkg = result.evidence_packages[0]
    # A well-connected candidate lands in the "moderate/high" band, not 1.0.
    assert 0.6 <= pkg.static_confidence <= 0.95
    assert pkg.confidence.sink_mapping == 1.0


# --- structural check classifier (no regex): detects real checks by shape -----


def test_structural_classifier_detects_scheme_and_signature(checked_result):
    """The variant with real checks must classify them structurally (symbol +
    operand), not by text — strncmp("https"...) and verify_signature(...)."""
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
