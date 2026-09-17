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
    expected_path = golden_path(fixture)
    if not expected_path.exists():
        pytest.skip(f"no golden snapshot: {expected_path.name}")
    assert dump(build_graphs(fixture)) == expected_path.read_text(encoding="utf-8"), (
        f"legacy chain output changed for {fixture.name}. If intended, rerun generate_golden.py and review the diff."
    )


@pytest.mark.parametrize("fixture", all_fixtures(), ids=_fixture_id)
def test_every_fixture_converts(fixture):
    assert build_template(fixture), f"{fixture.name} produced an empty template"


def test_java_sample_converts():
    java_sample = JAVA_FIXTURE
    if not java_sample.exists():
        pytest.skip(f"{java_sample.name} not present")
    assert build_template(java_sample), "Java sample produced an empty template"


def test_juliet_helper_still_filters_but_pipeline_does_not():
    template = build_template(next(p for p in all_fixtures() if p.name == "set_charging_profile.c.json"))
    names = function_names(template)

    assert names["unfiltered"] == ["store_charging_profile", "handle_set_charging_profile"]
    assert names["filtered"] == [], (
        "the Juliet name filter appears to have been removed -- if intentional, "
        "update this test and regenerate the golden snapshots"
    )


@pytest.mark.parametrize("fixture", all_fixtures(), ids=_fixture_id)
def test_graph_output_keys_match_gnn_contract(fixture):
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
    for fixture in all_fixtures():
        assert golden_path(fixture).exists(), f"missing snapshot for {fixture.name}"


def test_call_return_value_edges_are_emitted():
    fixture = next(p for p in all_fixtures() if p.name == "set_charging_profile_table.c.json")
    snapshot = build_graphs(fixture)
    ret_edges = [
        edge
        for function in snapshot["functions"]
        for edge in function["dfg"]["edges_dfg"]
        if str(edge[2].get("debug", {}).get("var_key", "")).startswith("$ret@")
    ]
    assert ret_edges, "no call return-value edges produced"


@pytest.mark.parametrize("fixture", all_fixtures(), ids=_fixture_id)
def test_no_external_method_stub_debris(fixture):
    template = build_template(fixture)

    assert [n.get("nodeType") for n in template] == ["TranslationUnit"], (
        f"{fixture.name} produced roots besides the TranslationUnit"
    )

    def stub_params(node, depth=0):
        found = []
        if node.get("nodeType") == "ParameterDeclaration" and node.get("type") == "ANY":
            found.append(node.get("name"))
        for child in node.get("children") or []:
            found.extend(stub_params(child, depth + 1))
        return found

    assert not [p for n in template for p in stub_params(n)], f"{fixture.name} still carries ANY-typed stub parameters"
