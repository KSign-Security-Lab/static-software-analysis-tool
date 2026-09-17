from __future__ import annotations

from ssat.schema_ts import output_path, render


def test_the_checked_in_file_matches_the_models() -> None:
    path = output_path()
    assert path.exists(), f"{path} is missing; run `python -m ssat.schema_ts --write`"
    assert path.read_text(encoding="utf-8") == render(), (
        f"{path} is out of date with ssat.f2a.models -- regenerate with `python -m ssat.schema_ts --write`"
    )


def test_nothing_renders_as_any() -> None:
    assert ": any" not in render()


def test_every_result_field_is_present() -> None:
    rendered = render()
    for field in (
        "source_cpg",
        "handler_maps",
        "handler_resolutions",
        "field_bindings",
        "flow_candidates",
        "sink_mappings",
        "expected_check_matchings",
        "missing_check_candidate_sets",
        "evidence_packages",
        "candidate_fragments",
        "limitations",
    ):
        assert f"  {field}:" in rendered or f"  {field}?:" in rendered, f"{field} is not in the generated schema"


def test_every_property_is_required() -> None:
    rendered = render()
    assert "  handler_maps: HandlerMap[];" in rendered
    assert "  handler_maps?:" not in rendered
