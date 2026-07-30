"""Characterization tests for the analysis chain outside F2-A.

These pin down what the pipeline produces, so the refactor can move and delete
code without silently changing behaviour. The golden snapshots record *current*
output -- they answer "did this change?", never "is this right?". Regenerate
with ``python packages/ssat/tests/generate_golden.py`` and review the diff; an
unexplained change here is a regression.
"""

from __future__ import annotations

import json

import pytest

from legacy_chain import (
    JAVA_FIXTURE,
    all_fixtures,
    build_graphs,
    build_template,
    dump,
    function_names,
    golden_path,
)


def _fixture_id(path):
    return path.name.removesuffix(".c.json")


@pytest.mark.parametrize("fixture", all_fixtures(), ids=_fixture_id)
def test_legacy_chain_matches_golden(fixture):
    """CPG -> template -> AST -> DFG produces byte-identical output."""
    expected_path = golden_path(fixture)
    if not expected_path.exists():
        pytest.skip(f"no golden snapshot: {expected_path.name}")
    assert dump(build_graphs(fixture)) == expected_path.read_text(encoding="utf-8"), (
        f"legacy chain output changed for {fixture.name}. If intended, rerun generate_golden.py and review the diff."
    )


@pytest.mark.parametrize("fixture", all_fixtures(), ids=_fixture_id)
def test_every_fixture_converts(fixture):
    """Template conversion succeeds for every fixture.

    Four of these used to raise. Any assignment with an ``<operator>.alloc``
    child crashed the converter, because its GraphSON unwrapper returned the
    property list (``["char[64]"]``) where callers expected the scalar. That was
    4/19 fixtures here and ~37% of the real corpus under ``results/``.
    """
    assert build_template(fixture), f"{fixture.name} produced an empty template"


def test_java_sample_converts():
    """Coverage for a non-C front end; it hit the same unwrapping defect.

    Kept out of the parametrized fixture set because at 5.9 MB it is too large
    to snapshot, but it is still a real test input -- hence fixtures/java/
    rather than artifacts/.
    """
    java_sample = JAVA_FIXTURE
    if not java_sample.exists():
        pytest.skip(f"{java_sample.name} not present")
    assert build_template(java_sample), "Java sample produced an empty template"


def test_juliet_helper_still_filters_but_pipeline_does_not():
    """The Juliet filter is now opt-in rather than the pipeline's default.

    ``ssat.ast.utils.get_juliet_benchmark_functions`` still requires the name to
    match ``bad|good|sink`` -- that is its purpose, and the name now says so.
    What changed is that ``ssat.pipeline`` no longer routes through it, so
    ``generate_ast`` finds functions in real-world code instead of silently
    returning an empty list.
    """
    template = build_template(next(p for p in all_fixtures() if p.name == "set_charging_profile.c.json"))
    names = function_names(template)

    assert names["unfiltered"] == ["store_charging_profile", "handle_set_charging_profile"]
    assert names["filtered"] == [], (
        "the Juliet name filter appears to have been removed -- if intentional, "
        "update this test and regenerate the golden snapshots"
    )


@pytest.mark.parametrize("fixture", all_fixtures(), ids=_fixture_id)
def test_graph_output_keys_match_gnn_contract(fixture):
    """The extractor output keys are what the GNN dataset loader reads.

    ``agent.dataset.JsonDataset`` builds the AST graph from every ``edges_*``
    key and the DFG graph from ``edges_dfg`` specifically. Renaming these keys
    breaks training silently, so pin them.
    """
    snapshot = json.loads(golden_path(fixture).read_text(encoding="utf-8"))
    for function in snapshot["functions"]:
        assert set(function["ast"]) == {
            "nodes",
            "edges_ast_pc",
            "edges_ast_sb",
            "edges_ast_guard",
        }
        assert set(function["dfg"]) == {"nodes", "edges_dfg"}


def test_every_fixture_has_a_snapshot():
    """No fixture is silently skipped by the golden set."""
    for fixture in all_fixtures():
        assert golden_path(fixture).exists(), f"missing snapshot for {fixture.name}"


def test_call_return_value_edges_are_emitted():
    """``x = f(...)`` must produce a ``$ret@<call>`` data-flow edge.

    Two instance attributes the DFG extractor relied on were never assigned:
    ``self.sb_edges`` (read by ``_sb_has``, whose bare ``except`` swallowed the
    AttributeError and returned False) and ``self.orig2sid``. Between them the
    call-to-assignment return-value edge could never be emitted. Both are built
    in ``__init__`` now; this pins the resulting edges so the fix cannot be
    silently undone.
    """
    fixture = next(p for p in all_fixtures() if p.name == "set_charging_profile_table.c.json")
    snapshot = build_graphs(fixture)

    ret_edges = [
        edge
        for function in snapshot["functions"]
        for edge in function["dfg"]["edges_dfg"]
        if str(edge[2].get("debug", {}).get("var_key", "")).startswith("$ret@")
    ]
    assert ret_edges, "no call return-value edges produced"
