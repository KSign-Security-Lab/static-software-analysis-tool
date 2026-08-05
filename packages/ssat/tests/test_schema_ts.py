"""The generated F2-A TypeScript must match the pydantic models.

Mirrors ``packages/agent/tests/test_schema.py``. The web app used to mirror
these types by hand and had already drifted -- ``F2AResult`` was missing four of
its eleven fields, which TypeScript cannot report, because a property absent
from an interface is not an error at the point it is read. This is the guard
that makes the generated copy trustworthy.
"""

from __future__ import annotations

from ssat.schema_ts import output_path, render


def test_the_checked_in_file_matches_the_models() -> None:
    """If this fails, run `python -m ssat.schema_ts --write` and commit the diff."""
    path = output_path()
    assert path.exists(), f"{path} is missing; run `python -m ssat.schema_ts --write`"
    assert path.read_text(encoding="utf-8") == render(), (
        f"{path} is out of date with ssat.f2a.models -- regenerate with `python -m ssat.schema_ts --write`"
    )


def test_nothing_renders_as_any() -> None:
    """An `any` here would be exactly the drift the generator exists to prevent."""
    assert ": any" not in render()


def test_every_result_field_is_present() -> None:
    """The four that were missing by hand, and the seven that were not.

    Named individually rather than counted, because a count passes just as
    happily when one field is swapped for another.
    """
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
    """`all_present` is on for this schema.

    Every field here carries a pydantic default, so without it the whole file
    renders optional and every read downstream needs a `?? []` -- for values the
    server always serialises in full.
    """
    rendered = render()
    assert "  handler_maps: HandlerMap[];" in rendered
    assert "  handler_maps?:" not in rendered
