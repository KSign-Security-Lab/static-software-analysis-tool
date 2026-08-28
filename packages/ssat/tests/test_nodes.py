"""Tests for the node readers shared by the AST and DFG extractors.

:mod:`ssat.nodes` was extracted from two copies that had already drifted. Two of
those divergences are deliberate and load-bearing, so they are pinned here: if
someone "simplifies" either one away, these fail rather than the goldens moving.
"""

from __future__ import annotations

from ssat.nodes import (
    fullname_from_expr,
    guards_from_condition_ast,
    guards_from_for_header,
    int_from_literal_node,
    int_from_node,
    member_parts,
    unwrap_ast,
    unwrap_cast_paren,
    unwrap_cast_typeref,
)


def ident(name):
    return {"nodeType": "Identifier", "name": name}


def lit(value, type_="int"):
    return {"nodeType": "Literal", "value": str(value), "type": type_, "code": str(value)}


def binary(op, *children):
    return {"nodeType": "BinaryExpression", "operator": op, "children": list(children)}


def member(base, field):
    return {"nodeType": "MemberAccess", "children": [ident(base), ident(field)]}


# ---------------------------------------------------------------------------
# guards from a condition
# ---------------------------------------------------------------------------


def test_lower_bound_only_for_comparison_against_zero():
    """``x > 0`` is a lower bound; ``x > 5`` is not recorded as one."""
    assert guards_from_condition_ast(binary(">", ident("i"), lit(0))) == {
        "i": {"lower": 1, "upper": 0, "upper_const": 0.0}
    }
    assert guards_from_condition_ast(binary(">", ident("i"), lit(5))) == {}


def test_upper_bound_normalizes_the_constant():
    assert guards_from_condition_ast(binary("<", ident("n"), lit(10))) == {
        "n": {"lower": 0, "upper": 1, "upper_const": 0.1}
    }


def test_non_constant_upper_bound_has_no_normalized_value():
    """``x < N`` is still an upper bound, but there is nothing to normalize."""
    assert guards_from_condition_ast(binary("<", ident("x"), ident("N"))) == {
        "x": {"lower": 0, "upper": 1, "upper_const": 0.0}
    }


def test_flipped_comparison_is_read_in_the_right_direction():
    """``10 > x`` means ``x < 10``, and ``0 < x`` means ``x > 0``."""
    assert guards_from_condition_ast(binary(">", lit(10), ident("x"))) == {
        "x": {"lower": 0, "upper": 1, "upper_const": 0.1}
    }
    assert guards_from_condition_ast(binary("<", lit(0), ident("x"))) == {
        "x": {"lower": 1, "upper": 0, "upper_const": 0.0}
    }


def test_both_sides_of_a_logical_operator_are_merged():
    """``&&`` and ``||`` alike: the union, conservatively."""
    cond = binary("&&", binary(">", ident("i"), lit(0)), binary("<", ident("i"), lit(4)))
    assert guards_from_condition_ast(cond) == {"i": {"lower": 1, "upper": 1, "upper_const": 0.25}}
    assert guards_from_condition_ast(binary("||", *cond["children"])) == guards_from_condition_ast(cond)


def test_the_tightest_upper_bound_wins():
    cond = binary("&&", binary("<", ident("i"), lit(10)), binary("<", ident("i"), lit(2)))
    assert guards_from_condition_ast(cond)["i"]["upper_const"] == 0.5


def test_guards_are_field_sensitive():
    cond = binary("<", member("req", "len"), lit(4))
    assert "req.len" in guards_from_condition_ast(cond)


def test_a_condition_nested_under_wrappers_is_still_found():
    wrapped = {"nodeType": "ParenExpression", "children": [binary("<", ident("x"), lit(2))]}
    assert guards_from_condition_ast(wrapped) == {"x": {"lower": 0, "upper": 1, "upper_const": 0.5}}


def test_no_guards_from_a_non_comparison():
    assert guards_from_condition_ast(binary("+", ident("a"), ident("b"))) == {}
    assert guards_from_condition_ast(None) == {}


# ---------------------------------------------------------------------------
# guards from a for header
# ---------------------------------------------------------------------------


def for_stmt(init, cond, inc):
    return {"nodeType": "ForStatement", "children": [init, cond, inc]}


def assign(op, lhs, rhs):
    return {"nodeType": "AssignmentExpression", "operator": op, "children": [lhs, rhs]}


def unary(op, operand):
    return {"nodeType": "UnaryExpression", "operator": op, "children": [operand]}


def test_canonical_counting_loop_grants_a_lower_bound():
    loop = for_stmt(assign("=", ident("i"), lit(0)), None, unary("++", ident("i")))
    assert guards_from_for_header(loop) == {"i": {"lower": 1, "upper": 0, "upper_const": 0.0}}


def test_negative_start_grants_nothing():
    loop = for_stmt(assign("=", ident("i"), lit(-1)), None, unary("++", ident("i")))
    assert guards_from_for_header(loop) == {}


def test_decrementing_loop_grants_nothing():
    loop = for_stmt(assign("=", ident("i"), lit(0)), None, unary("--", ident("i")))
    assert guards_from_for_header(loop) == {}


def test_a_different_variable_in_the_increment_grants_nothing():
    loop = for_stmt(assign("=", ident("i"), lit(0)), None, unary("++", ident("j")))
    assert guards_from_for_header(loop) == {}


def test_compound_step_must_be_non_negative():
    grows = for_stmt(assign("=", ident("i"), lit(0)), None, assign("+=", ident("i"), lit(2)))
    shrinks = for_stmt(assign("=", ident("i"), lit(0)), None, assign("+=", ident("i"), lit(-2)))
    assert guards_from_for_header(grows) == {"i": {"lower": 1, "upper": 0, "upper_const": 0.0}}
    assert guards_from_for_header(shrinks) == {}


def test_a_non_for_node_yields_nothing():
    assert guards_from_for_header(binary("<", ident("i"), lit(4))) == {}


# ---------------------------------------------------------------------------
# the two deliberate divergences
# ---------------------------------------------------------------------------


def test_the_two_literal_readers_are_deliberately_different():
    """``int_from_node`` and ``int_from_literal_node`` must not be merged.

    The condition reader requires an int-ish ``type`` but will scrape the code
    text when ``value`` is unusable; the for-header reader ignores ``type`` and
    gives up instead. Each is what its caller had.
    """
    untyped = {"nodeType": "Literal", "value": "7", "type": "char", "code": "7"}
    assert int_from_node(untyped) is None, "condition reader honours `type`"
    assert int_from_literal_node(untyped) == 7, "for-header reader ignores `type`"

    unparseable = {"nodeType": "Literal", "value": None, "type": "int", "code": "16"}
    assert int_from_node(unparseable) == 16, "condition reader falls back to the code text"
    assert int_from_literal_node(unparseable) is None, "for-header reader gives up"


def test_the_two_cast_peeling_strategies_are_deliberately_different():
    """``unwrap_cast_typeref`` skips a cast's type child; ``unwrap_cast_paren`` does not.

    ``fullname_from_expr`` therefore takes the strategy as an argument. The AST
    extractor passes the first, the DFG extractor the second.
    """
    cast = {
        "nodeType": "CastExpression",
        "children": [{"nodeType": "TypeRef", "name": "char"}, ident("buf")],
    }
    assert unwrap_cast_typeref(cast) == ident("buf")
    assert unwrap_cast_paren(cast) == {"nodeType": "TypeRef", "name": "char"}

    assert fullname_from_expr(cast, unwrap=unwrap_cast_typeref) == "buf"
    assert fullname_from_expr(cast, unwrap=unwrap_cast_paren) is None

    paren = {"nodeType": "ParenExpression", "children": [ident("x")]}
    assert unwrap_cast_paren(paren) == ident("x"), "only this strategy peels parentheses"
    assert unwrap_cast_typeref(paren) == paren


# ---------------------------------------------------------------------------
# expression readers
# ---------------------------------------------------------------------------


def test_fullname_reaches_through_deref_and_subscript():
    subscript = {"nodeType": "ArraySubscriptExpression", "children": [member("s", "buf"), ident("i")]}
    assert fullname_from_expr(subscript, unwrap=unwrap_cast_typeref) == "s.buf"

    deref = {"nodeType": "PointerDereference", "children": [ident("p")]}
    assert fullname_from_expr(deref, unwrap=unwrap_cast_typeref) == "p"

    addr = unary("&", member("req", "id"))
    assert fullname_from_expr(addr, unwrap=unwrap_cast_typeref) == "req.id"


def test_fullname_of_something_that_names_nothing():
    assert fullname_from_expr(None, unwrap=unwrap_cast_typeref) is None
    assert fullname_from_expr(lit(3), unwrap=unwrap_cast_typeref) is None


def test_member_parts_splits_base_and_field():
    assert member_parts(member("s", "buf")) == ("s", "buf", "s.buf")
    assert member_parts(ident("x")) == (None, None, None)


def test_unwrap_ast_strips_only_what_it_is_asked_to():
    addr = {"nodeType": "AddressOfExpression", "children": [ident("x")]}
    assert unwrap_ast(addr, strip_addr=False) == addr
    assert unwrap_ast(addr, strip_addr=True) == ident("x")
