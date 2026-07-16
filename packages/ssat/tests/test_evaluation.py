"""Smoke test for the F2-A evaluation harness over the synthetic CPG fixtures.

Verifies deterministic output, metric correctness, per-action traceability, the
locked taxonomy, and the analysis-scope vs supportable-shape separation. No real
corpus and no Joern needed (CPG mode over committed fixtures).
"""

from pathlib import Path

from ssat.f2a.evaluation import (
    TIER_ANALYSIS_SCOPE,
    TIER_POLICY,
    TIER_POTENTIALLY_SUPPORTABLE,
    TIER_UNKNOWN,
    deterministic_view,
    evaluate_cpg_dir,
    render_markdown,
)

FX = Path(__file__).parent / "fixtures" / "f2a" / "cpg"


def _run():
    return evaluate_cpg_dir(FX, corpus_id="synthetic", timestamp="FIXED")


def _rec(report, corpus_file, action):
    return next(
        r for r in report["actions"]
        if r["corpus_file"] == corpus_file and r["action"] == action
    )


def test_report_is_deterministic():
    a, b = _run(), _run()
    # metrics + per-action records reproduce exactly; run metadata/perf excluded.
    assert deterministic_view(a) == deterministic_view(b)


def test_report_shape_has_all_five_areas():
    m = _run()["metrics"]
    for key in (
        "outcome_counts",                # 1
        "unresolved_reason_histogram",   # 2 (+ tier_histogram)
        "tier_histogram",
        "backend_histogram",             # 3
        "resolved_confidence",           # 4
        "corroboration_lift",
        "margin",
        "evidence_volume",               # 5
        "candidate_volume",
    ):
        assert key in m, key


def test_outcomes_cover_all_three_statuses():
    m = _run()["metrics"]["outcome_counts"]
    assert m["RESOLVED"] >= 1
    assert m["AMBIGUOUS"] >= 1
    assert m["UNRESOLVED"] >= 1


def test_reason_histogram_excludes_ambiguous():
    # AMBIGUOUS is not an unresolved *reason*; it lives in tier/backend histograms.
    m = _run()["metrics"]
    assert "NONE" not in m["unresolved_reason_histogram"]
    assert m["tier_histogram"].get(TIER_POLICY, 0) >= 1  # the ambiguous case


def test_analysis_scope_and_supportable_kept_separate():
    hist = _run()["metrics"]["tier_histogram"]
    # the four tiers are distinct buckets; supportable != scope != policy != unknown
    assert set(hist) <= {
        TIER_ANALYSIS_SCOPE, TIER_POTENTIALLY_SUPPORTABLE, TIER_POLICY, TIER_UNKNOWN,
    }


def test_ambiguous_record_classification():
    r = _rec(_run(), "scp_ambiguous_two_registrations.c.json", "SetChargingProfile")
    assert r["status"] == "AMBIGUOUS"
    c = r["classification"]
    assert c["tier"] == TIER_POLICY
    assert c["backend_category"] == "COMPETING_CANDIDATES"
    assert c["classification_confidence"] == "HIGH"
    assert c["supporting_observations"]  # non-empty


def test_registrar_store_not_reached_is_supportable_low_confidence():
    r = _rec(_run(), "scp_registrar_no_store.c.json", "SetChargingProfile")
    assert r["status"] == "UNRESOLVED"
    assert r["unresolved_reason"] == "REGISTRAR_STORE_NOT_REACHED"
    c = r["classification"]
    assert c["tier"] == TIER_POTENTIALLY_SUPPORTABLE
    assert c["classification_confidence"] == "LOW"  # not claimed with certainty


def test_resolved_records_are_traceable():
    report = _run()
    dt = _rec(report, "data_transfer_reg_vs_switch.c.json", "DataTransfer")
    assert dt["status"] == "RESOLVED" and dt["chosen_function"] == "bar"
    d = _rec(report, "scp_registrar_direct.c.json", "SetChargingProfile")
    assert d["status"] == "RESOLVED" and d["chosen_function"] == "on_scp"


def test_every_unresolved_has_a_classification_with_observations():
    for r in _run()["actions"]:
        if r["status"] != "RESOLVED":
            c = r["classification"]
            assert c is not None
            assert c["tier"] in {
                TIER_ANALYSIS_SCOPE, TIER_POTENTIALLY_SUPPORTABLE, TIER_POLICY, TIER_UNKNOWN,
            }
            assert isinstance(c["supporting_observations"], list) and c["supporting_observations"]


def test_no_evidence_absent_action_is_unknown_not_false_cross_tu():
    # an action absent from a TU must not be labelled CROSS_TU with certainty.
    r = _rec(_run(), "update_firmware.c.json", "RemoteStartTransaction")
    assert r["status"] == "UNRESOLVED"
    assert r["classification"]["tier"] == TIER_UNKNOWN
    assert r["classification"]["classification_confidence"] == "LOW"


def test_markdown_renders():
    md = render_markdown(_run())
    assert "# F2-A handler-resolution evaluation" in md
    assert "Resolution outcomes" in md
