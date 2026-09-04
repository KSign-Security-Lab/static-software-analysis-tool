"""`#define` macros, which Joern models as calls.

Joern runs no preprocessor. It emits a macro definition as an external METHOD
and every *use* as a CALL, hanging the expansion under the use site as an
ordinary AST subtree. The template folds that pseudo-call into the expansion so
a macro bound reads as the number it is and a macro-wrapped call is attributed
to the callee it really names.

The unit tests below pin the fold itself; the two at the end run the whole chain
over real Joern output, which is the only thing that proves the shape is what we
think it is.
"""

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


# -- the fold ---------------------------------------------------------------


def test_an_object_like_macro_yields_the_constant_it_stands_for():
    """`#define MAX 512` used as a bound: the block holds just the literal."""
    found = _macro_expansion([block([literal(512)])])

    assert found is not None
    assert found["nodeType"] == "Literal"
    assert found["value"] == "512"


def test_a_function_like_macro_yields_the_call_it_wraps():
    """The actual arguments sit *beside* the block and are already substituted
    inside it, so the expansion alone carries the whole meaning."""
    found = _macro_expansion([ident("dst"), ident("src"), block([call("strcpy", [])])])

    assert found is not None
    assert found["name"] == "strcpy"


def test_an_ordinary_call_is_left_alone():
    """A real argument list holds expressions, never a statement."""
    assert _macro_expansion([ident("dst"), ident("src")]) is None


def test_a_block_holding_more_than_one_node_is_left_alone():
    """Two statements is not an expansion this can stand in for."""
    assert _macro_expansion([block([literal(1), literal(2)])]) is None


def test_two_blocks_are_left_alone():
    """Ambiguous, so it declines rather than guessing which one is the value."""
    assert _macro_expansion([block([literal(1)], 3), block([literal(2)], 5)]) is None


def test_an_empty_block_is_left_alone():
    """An include guard expands to nothing; there is no value to substitute."""
    assert _macro_expansion([block([])]) is None


# -- end to end, over real Joern output -------------------------------------


def _graphs(fixture_name, function_name, *, replace_macro=True):
    """Run CPG -> template -> AST + DFG for one function of one fixture."""
    cpg = _load_cpg(CPG_FIXTURES / fixture_name)
    with contextlib.redirect_stdout(io.StringIO()):
        template = generate_template(cpg, replace_macro=replace_macro)
        function = next(f for f in get_functions_from_template(template) if f.get("name") == function_name)
        ast = ASTExtractor(function).run()
        dfg = DFGExtractor(function, ast).run()
    return ast, dfg


def test_a_macro_bound_becomes_a_real_upper_bound():
    """The headline. `if (length < MAX_PAYLOAD)` was indistinguishable from an
    unguarded copy, because the bound reader only accepts an integer literal and
    the macro arrived as a pseudo-call.
    """
    ast, _ = _graphs("macro_bound.c.json", "store_payload")
    bounds = [n["feat"]["ctx_upper_bound_norm"] for n in ast["nodes"]]

    assert max(bounds) == 1 / 256, "the bound should read as 1/MAX_PAYLOAD"


def test_without_the_fold_the_same_bound_reads_as_absent():
    """What `--no-replace-macro` restores, and what the bug was: 0.0 is exactly
    what a copy with no guard at all reports.
    """
    ast, _ = _graphs("macro_bound.c.json", "store_payload", replace_macro=False)

    assert max(n["feat"]["ctx_upper_bound_norm"] for n in ast["nodes"]) == 0.0


def test_the_validated_ast_stage_accepts_a_resolved_bound():
    """`generate_ast` validates, and the schema said these were integers.

    Nothing caught it because every bound was 0.0, which coerces. The first
    resolvable one is 1/256, which does not -- so the stage that folds macros
    would have raised instead of reporting them.
    """
    from ssat.pipeline import generate_ast

    cpg = _load_cpg(CPG_FIXTURES / "macro_bound.c.json")
    with contextlib.redirect_stdout(io.StringIO()):
        results = generate_ast(generate_template(cpg))

    assert max(n["feat"]["ctx_upper_bound_norm"] for r in results for n in r["nodes"]) == 1 / 256


def test_a_macro_wrapped_sink_is_attributed_to_the_real_callee():
    """Joern inlines the expansion, so the copy was always *found* -- but the
    node was named after the macro, so its type and semantic category came from
    a name that is in no table.
    """
    ast, dfg = _graphs("macro_wrapped_sink.c.json", "set_firmware_url")
    calls = [n for n in ast["nodes"] if "strcpy" in (n.get("code") or "")]

    assert calls, "the wrapped strcpy should be a statement in its own right"
    assert calls[0]["node_type"] == "StandardLibCall"
    unbounded = [n["feat"]["is_sink_call_unbounded"] for n in dfg["nodes"] if n["sid"] == calls[0]["sid"]]
    assert unbounded == [1]


def test_without_the_fold_the_sink_keeps_the_macro_name():
    """The other half of the same fact: detection did not depend on the fold,
    attribution did.
    """
    ast, _ = _graphs("macro_wrapped_sink.c.json", "set_firmware_url", replace_macro=False)
    named = [n for n in ast["nodes"] if n.get("node_type") == "UserDefinedCall"]

    assert [n["code"] for n in named] == ["COPY_URL(dst, src)"]
