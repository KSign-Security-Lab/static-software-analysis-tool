"""Regression tests for defects in the DFG extractor.

Each test here pins a specific bug that was fixed, with enough of a comment to
say what went wrong -- the golden snapshots cover "did output change", not "is
this input handled at all".
"""

from __future__ import annotations

import pytest

from ssat.ast.extractor import ASTExtractor
from ssat.dfg.extractor import DFGExtractor


def ident(name, node_id):
    return {"nodeType": "Identifier", "name": name, "id": node_id, "code": name, "children": []}


def literal(value, node_id):
    return {
        "nodeType": "Literal",
        "value": str(value),
        "type": "int",
        "id": node_id,
        "code": str(value),
        "children": [],
    }


def function(body):
    """A FunctionDefinition wrapping ``body`` in a compound statement."""
    return {
        "nodeType": "FunctionDefinition",
        "name": "f",
        "code": "void f(void)",
        "id": 1,
        "children": [{"nodeType": "CompoundStatement", "id": 2, "code": "{ ... }", "children": body}],
    }


def array_write():
    """``buf[0] = 1;``"""
    subscript = {
        "nodeType": "ArraySubscriptExpression",
        "id": 10,
        "code": "buf[0]",
        "children": [ident("buf", 11), literal(0, 12)],
    }
    return {
        "nodeType": "AssignmentExpression",
        "operator": "=",
        "id": 13,
        "code": "buf[0] = 1",
        "children": [subscript, literal(1, 14)],
    }


def array_decl():
    return {
        "nodeType": "ArrayDeclaration",
        "name": "buf",
        "length": "8",
        "id": 20,
        "code": "char buf[8]",
        "children": [],
    }


def graphs(body):
    fn = function(body)
    ast_result = ASTExtractor(fn).run()
    return DFGExtractor(fn, ast_result, sink_mode="k1").run()


def def_vars(dfg):
    return {n["sid"]: n["debug"]["def_vars"] for n in dfg["nodes"]}


@pytest.mark.parametrize(
    "body,label",
    [
        ([array_write()], "as the only statement"),
        ([array_decl(), array_write()], "after a declaration"),
    ],
)
def test_writing_to_an_array_element_does_not_crash(body, label):
    """``buf[0] = 1`` used to raise NameError when no call preceded it.

    The array-subscript branch tested ``isinstance(base, dict)``, where ``base``
    was the *callee name string* leaked from the call-handling block earlier in
    the same loop -- it meant to test ``base_node``, the subscript's base. So the
    branch was unreachable whenever ``base`` was set (a str is never a dict), and
    raised NameError when it wasn't, which is any function whose first
    array-element write is not preceded by a call.
    """
    assert "buf" in def_vars(graphs(body))[1], f"array element write {label} should define its base"


def test_the_base_of_an_array_write_is_recorded_as_a_definition():
    """The consequence of the bug above: the "object write" path was dead.

    With ``base`` misread, ``lhs_is_object_base`` never became True for a
    subscript LHS, so the base was never added to ``def_vars`` by that path.
    """
    dfg = graphs([array_decl(), array_write()])
    written = [sid for sid, names in def_vars(dfg).items() if "buf" in names]
    assert written, "no statement claims to define buf"
