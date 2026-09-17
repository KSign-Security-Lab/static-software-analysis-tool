from __future__ import annotations

import contextlib
import io

from legacy_chain import _load_cpg, CPG_FIXTURES

from ssat.ast.extractor import ASTExtractor
from ssat.dfg.extractor import DFGExtractor
from ssat.pipeline import generate_template
from ssat.template.converter import _macro_expansion
from ssat.utils import get_functions_from_template


def literal(value, node_id=1):
    return {
        "nodeType": "Literal",
        "type": "int",
        "value": str(value),
        "code": str(value),
        "id": node_id,
        "children": [],
    }


def ident(name, node_id=2):
    return {"nodeType": "Identifier", "name": name, "code": name, "id": node_id, "children": []}


def block(children, node_id=3):
    return {"nodeType": "CompoundStatement", "code": "<empty>", "id": node_id, "children": children}


def call(name, children, node_id=4):
    return {"nodeType": "StandardLibCall", "name": name, "code": f"{name}(...)", "id": node_id, "children": children}


def test_an_object_like_macro_yields_the_constant_it_stands_for():
    found = _macro_expansion([block([literal(512)])])

    assert found is not None
    assert found["nodeType"] == "Literal"
    assert found["value"] == "512"


def test_a_function_like_macro_yields_the_call_it_wraps():
    found = _macro_expansion([ident("dst"), ident("src"), block([call("strcpy", [])])])

    assert found is not None
    assert found["name"] == "strcpy"


def test_an_ordinary_call_is_left_alone():
    assert _macro_expansion([ident("dst"), ident("src")]) is None


def test_a_block_holding_more_than_one_node_is_left_alone():
    assert _macro_expansion([block([literal(1), literal(2)])]) is None


def test_two_blocks_are_left_alone():
    assert _macro_expansion([block([literal(1)], 3), block([literal(2)], 5)]) is None


def test_an_empty_block_is_left_alone():
    assert _macro_expansion([block([])]) is None


def _graphs(fixture_name, function_name, *, replace_macro=True):
    cpg = _load_cpg(CPG_FIXTURES / fixture_name)
    with contextlib.redirect_stdout(io.StringIO()):
        template = generate_template(cpg, replace_macro=replace_macro)
        function = next(f for f in get_functions_from_template(template) if f.get("name") == function_name)
        ast = ASTExtractor(function).run()
        dfg = DFGExtractor(function, ast).run()
    return ast, dfg


def test_a_macro_bound_becomes_a_real_upper_bound():
    ast, _ = _graphs("macro_bound.c.json", "store_payload")
    bounds = [n["feat"]["ctx_upper_bound_norm"] for n in ast["nodes"]]

    assert max(bounds) == 1 / 256, "the bound should read as 1/MAX_PAYLOAD"


def test_without_the_fold_the_same_bound_reads_as_absent():
    ast, _ = _graphs("macro_bound.c.json", "store_payload", replace_macro=False)

    assert max(n["feat"]["ctx_upper_bound_norm"] for n in ast["nodes"]) == 0.0


def test_the_validated_ast_stage_accepts_a_resolved_bound():
    from ssat.pipeline import generate_ast

    cpg = _load_cpg(CPG_FIXTURES / "macro_bound.c.json")
    with contextlib.redirect_stdout(io.StringIO()):
        results = generate_ast(generate_template(cpg))

    assert max(n["feat"]["ctx_upper_bound_norm"] for r in results for n in r["nodes"]) == 1 / 256


def test_a_macro_wrapped_sink_is_attributed_to_the_real_callee():
    ast, dfg = _graphs("macro_wrapped_sink.c.json", "set_firmware_url")
    calls = [n for n in ast["nodes"] if "strcpy" in (n.get("code") or "")]

    assert calls, "the wrapped strcpy should be a statement in its own right"
    assert calls[0]["node_type"] == "StandardLibCall"
    unbounded = [n["feat"]["is_sink_call_unbounded"] for n in dfg["nodes"] if n["sid"] == calls[0]["sid"]]
    assert unbounded == [1]


def test_without_the_fold_the_sink_keeps_the_macro_name():
    ast, _ = _graphs("macro_wrapped_sink.c.json", "set_firmware_url", replace_macro=False)
    named = [n for n in ast["nodes"] if n.get("node_type") == "UserDefinedCall"]

    assert [n["code"] for n in named] == ["COPY_URL(dst, src)"]
