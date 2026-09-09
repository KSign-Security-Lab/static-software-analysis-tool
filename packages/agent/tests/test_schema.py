from __future__ import annotations

import pytest

from agent.ids import finding_id, normalize_anchor, normalize_cwe
from agent.schema import (
    SCHEMA_VERSION,
    CandidateFinding,
    ChunkAnalysis,
    Finding,
    Remediation,
    Report,
    Span,
    Verdict,
)
from agent.schema_ts import output_path, render


def _finding(**overrides: object) -> Finding:
    base: dict[str, object] = {
        "id": "abc123",
        "chunk_id": "chunk1",
        "severity": "high",
        "confidence": 0.8,
        "title": "Command injection",
        "cwe": "CWE-78",
        "primary": Span(file="a.c", start_line=5, start_column=3, end_line=5, end_column=20, excerpt="system(cmd);"),
        "explanation": "why",
        "remediation": Remediation(summary="s", detail="d"),
        "verified": True,
    }
    base.update(overrides)
    return Finding(**base)  # type: ignore[arg-type]


def test_generated_typescript_matches_the_models() -> None:
    path = output_path()
    assert path.exists(), f"{path} has never been generated"
    assert path.read_text(encoding="utf-8") == render(), (
        "web/lib/agent-schema.ts is out of date with agent/schema.py -- "
        "regenerate with `python -m agent.schema_ts --write`"
    )


def test_generator_refuses_to_emit_any() -> None:
    assert ": any" not in render()


def test_finding_id_is_stable_across_runs() -> None:
    args = {"file": "a.c", "symbol": "handler", "cwe": "CWE-78", "anchor_text": "system(cmd);"}
    assert finding_id(**args) == finding_id(**args)


def test_finding_id_ignores_reformatting_and_position() -> None:
    tight = finding_id(file="a.c", symbol="handler", cwe="CWE-78", anchor_text="system(cmd);")
    spaced = finding_id(file="a.c", symbol="handler", cwe="CWE-78", anchor_text="system( cmd );\n")
    assert tight == finding_id(file="a.c", symbol="handler", cwe="CWE-78", anchor_text="  system(cmd);  ")
    assert spaced != tight, "whitespace inside the expression is still a different anchor"
    assert normalize_anchor("a  \n  b") == "a b"


def test_finding_id_distinguishes_real_differences() -> None:
    base = {"file": "a.c", "symbol": "handler", "cwe": "CWE-78", "anchor_text": "system(cmd);"}
    assert finding_id(**{**base, "file": "b.c"}) != finding_id(**base)
    assert finding_id(**{**base, "symbol": "other"}) != finding_id(**base)
    assert finding_id(**{**base, "cwe": "CWE-77"}) != finding_id(**base)
    assert finding_id(**{**base, "anchor_text": "exec(cmd);"}) != finding_id(**base)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("CWE-78", "CWE-78"),
        ("cwe 78", "CWE-78"),
        ("CWE_078", "CWE-78"),
        ("CWE‑078", "CWE-78"),
        (None, None),
        ("", None),
        ("no identifier here", None),
    ],
)
def test_normalize_cwe_canonicalises_or_gives_up(raw: str | None, expected: str | None) -> None:
    assert normalize_cwe(raw) == expected


def test_normalize_cwe_survives_the_paragraph_a_real_model_returned() -> None:
    blob = (
        "[CWE-78](https://cwe.mitre.org/data/definitions/77.html) (Improper "
        "Neutralization of Special Elements used in a Command ('OS Command "
        "Injection')) or [ CWE-94: Code Injection ]( https://cwe.mitre.org/data/definitions/95 )"
    )
    assert normalize_cwe(blob) == "CWE-78", "the first identifier wins"


def test_normalized_cwe_keeps_ids_stable_across_phrasings() -> None:
    base = {"file": "a.c", "symbol": "handler", "anchor_text": "system(cmd);"}
    tidy = finding_id(**base, cwe=normalize_cwe("CWE-78"))
    messy = finding_id(**base, cwe=normalize_cwe("[CWE-78](https://cwe.mitre.org/...) OS Command Injection"))
    assert tidy == messy


def test_report_sorts_most_severe_first() -> None:
    report = Report(
        run_id="r1",
        findings=[
            _finding(id="low1", severity="low"),
            _finding(id="crit", severity="critical"),
            _finding(id="med", severity="medium"),
        ],
    )
    assert [f.id for f in report.sorted_findings()] == ["crit", "med", "low1"]


def test_schema_version_is_pinned_on_the_wire() -> None:
    assert _finding().model_dump()["schema_version"] == SCHEMA_VERSION
    assert Report(run_id="r").model_dump()["schema_version"] == SCHEMA_VERSION


def test_model_facing_schema_omits_server_owned_fields() -> None:
    candidate_fields = set(CandidateFinding.model_fields)
    assert not candidate_fields & {"id", "chunk_id", "primary", "verified", "confidence", "schema_version"}
    assert "anchor_text" in candidate_fields, "the model locates by quoting source, not by line number"


def test_chunk_analysis_carries_the_cross_chunk_note() -> None:
    assert "note" in ChunkAnalysis.model_fields
    assert ChunkAnalysis().note == "", "a chunk with nothing to say must be representable"


def test_verdict_defaults_are_hostile_to_the_finding() -> None:
    verdict = Verdict(refuted=True, reason="cannot substantiate", confidence=0.1)
    assert verdict.refuted is True
    assert 0.0 <= verdict.confidence <= 1.0


def test_remediation_diff_is_optional_and_defaults_to_absent() -> None:
    assert Remediation(summary="s", detail="d").diff is None
