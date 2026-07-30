"""The pipeline's training output must be loadable by the GNN dataset layer.

This contract was silently broken before the refactor: the CLI's ``full`` mode
wrote ``ast_result``/``dfg_result``, while ``agent.dataset.JsonDataset`` reads
top-level ``ast``/``dfg``. Nothing failed loudly -- the trainer just saw graphs
with no nodes. These tests fail loudly instead.
"""

from __future__ import annotations

import pytest

from legacy_chain import all_fixtures

pytest.importorskip("torch", reason="agent's GNN stack is not installed")


def _first_fixture_with_functions():
    from ssat.pipeline import analyze_cpg

    import json

    for path in all_fixtures():
        cpg = {"export": json.loads(path.read_text(encoding="utf-8"))}
        graphs = analyze_cpg(cpg, source=str(path.name))
        if graphs:
            return graphs
    pytest.skip("no fixture produced functions")


def test_training_record_has_the_keys_the_loader_reads():
    from ssat.pipeline import training_record

    record = training_record(_first_fixture_with_functions()[0])
    # juliet_json_to_sample reads exactly these.
    assert "ast" in record and "dfg" in record
    assert record["ast"]["nodes"], "AST section must not be empty"
    assert "edges_dfg" in record["dfg"]
    assert record["function_name"]


def test_loader_builds_populated_ast_and_dfg_graphs():
    """The real round-trip: pipeline output -> juliet_json_to_sample -> Data."""
    from pydantic import BaseModel

    from agent.dataset.JsonDataset import juliet_json_to_sample
    from ssat.pipeline import training_record

    record = training_record(_first_fixture_with_functions()[0], include_template=False)

    class _Raw(BaseModel):
        """juliet_json_to_sample takes a pydantic model and calls model_dump()."""

        model_config = {"extra": "allow"}

    sample = juliet_json_to_sample(_Raw(**record))

    assert sample.ast_graph is not None
    assert sample.ast_graph.num_nodes > 0, "AST graph came back empty"
    assert getattr(sample, "dfg_graph", None) is not None, (
        "DFG graph missing -- the loader did not find a top-level 'dfg' key"
    )
    assert sample.dfg_graph.num_nodes > 0, "DFG graph came back empty"


def test_old_broken_schema_degenerates_silently():
    """Guard against regressing to ``ast_result``/``dfg_result``.

    Documents *why* the key names matter, and why the break went unnoticed: the
    old shape raises nothing. It yields an AST graph of one featureless node and
    no DFG graph at all -- a sample the trainer happily accepts and learns
    nothing from.
    """
    from pydantic import BaseModel

    from agent.dataset.JsonDataset import juliet_json_to_sample
    from ssat.pipeline import training_record

    record = training_record(_first_fixture_with_functions()[0], include_template=False)
    legacy_shape = {
        "file": record["function_name"],
        "ast_result": record["ast"],
        "dfg_result": record["dfg"],
    }

    class _Raw(BaseModel):
        model_config = {"extra": "allow"}

    sample = juliet_json_to_sample(_Raw(**legacy_shape))
    # A single placeholder node carrying zero features, and no DFG side at all.
    assert sample.ast_graph.num_nodes == 1
    assert sample.ast_graph.x.shape[1] == 0, "expected zero feature columns"
    assert sample.ast_graph.edge_index.shape[1] == 0, "expected no edges"
    assert getattr(sample, "dfg_graph", None) is None
