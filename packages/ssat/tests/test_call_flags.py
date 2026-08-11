"""Tests for the AST pass's per-call feature flags.

``compute_call_flags`` decides whether a bounded call is actually bounded: is the
size argument tied to the destination's own ``sizeof``, or does it describe
something else. The golden snapshots never exercise the struct-field half of that
-- none of the fixtures passes ``t.field`` to a sink -- so it is pinned here.

The call ASTs are built by hand rather than generated, because this reads only
the node shape and generating a CPG per case would cost a Joern run each.
"""

from __future__ import annotations

import pytest

from ssat.ast.extractor import ASTExtractor


def ident(name):
    return {"nodeType": "Identifier", "name": name, "code": name, "children": []}


def member(base, field):
    """``base.field`` -- base as a plain identifier, which is what makes it readable."""
    return {
        "nodeType": "MemberAccess",
        "code": f"{base}.{field}",
        "children": [ident(base), ident(field)],
    }


def arrow(base, field):
    """``base->field``, where the front end wraps the base in a dereference."""
    return {
        "nodeType": "MemberAccess",
        "code": f"{base}->{field}",
        "children": [
            {"nodeType": "PointerDereference", "code": base, "children": [ident(base)]},
            ident(field),
        ],
    }


def expr(code, node_type="Identifier"):
    return {"nodeType": node_type, "code": code, "children": []}


def call(name, *args):
    return {
        "nodeType": "StandardLibCall",
        "name": name,
        "code": f"{name}({', '.join(a.get('code', '') for a in args)})",
        "children": [{"nodeType": "ArgumentList", "code": "", "children": list(args)}],
    }


def flags_for(name, *args):
    node = call(name, *args)
    return ASTExtractor({"nodeType": "FunctionDefinition", "name": "f", "children": []}).compute_call_flags(
        fname=name, call_ast=node, code=node["code"]
    )


# ---------------------------------------------------------------------------
# size argument tied to the destination
# ---------------------------------------------------------------------------


def test_sizeof_the_destination_counts_as_bounded():
    f = flags_for("memcpy", ident("dst"), ident("src"), expr("sizeof(dst)"))
    assert f["call_flag_len_linked_to_dst"] == 1
    assert f["call_flag_sizeof_non_dst"] == 0


@pytest.mark.parametrize("size", ["sizeof(*dst)", "sizeof(dst[0])"])
def test_the_pointer_and_element_forms_count_too(size):
    assert flags_for("memcpy", ident("dst"), ident("src"), expr(size))["call_flag_len_linked_to_dst"] == 1


def test_sizeof_something_else_is_flagged_rather_than_trusted():
    """The dangerous case: a size that looks principled and is not."""
    f = flags_for("memcpy", ident("dst"), ident("src"), expr("sizeof(other)"))
    assert f["call_flag_sizeof_non_dst"] == 1
    assert f["call_flag_len_linked_to_dst"] == 0


def test_a_plain_variable_size_links_to_nothing_and_is_not_a_sizeof_claim():
    f = flags_for("memcpy", ident("dst"), ident("src"), expr("n"))
    assert f["call_flag_len_linked_to_dst"] == 0
    assert f["call_flag_sizeof_non_dst"] == 0


# ---------------------------------------------------------------------------
# struct-field destinations
# ---------------------------------------------------------------------------


def test_sizeof_the_field_is_the_extended_link():
    f = flags_for("memcpy", member("t", "buf"), ident("src"), expr("sizeof(t.buf)"))
    assert f["call_dst_is_field"] == 1
    assert f["call_len_linked_to_dst_extended"] == 1
    assert f["call_flag_len_linked_to_dst"] == 1
    assert f["call_size_mismatch_field"] == 0


def test_writing_one_field_but_sizing_the_whole_struct_is_a_mismatch():
    """``memcpy(t.buf, src, sizeof(t))`` -- the classic overrun of a bounded call."""
    f = flags_for("memcpy", member("t", "buf"), ident("src"), expr("sizeof(t)"))
    assert f["call_dst_is_field"] == 1
    assert f["call_size_is_sizeof_base_struct"] == 1
    assert f["call_size_mismatch_field"] == 1
    assert f["call_flag_len_linked_to_dst"] == 0


def test_a_field_destination_sized_by_an_unrelated_sizeof_is_also_a_mismatch():
    f = flags_for("memcpy", member("t", "buf"), ident("src"), expr("sizeof(other)"))
    assert f["call_size_mismatch_field"] == 1
    assert f["call_size_is_sizeof_base_struct"] == 0


def test_a_field_destination_with_a_variable_size_claims_nothing():
    """No `sizeof` anywhere, so there is no false claim of boundedness to flag."""
    f = flags_for("memcpy", member("t", "buf"), ident("src"), expr("n"))
    assert f["call_dst_is_field"] == 1
    assert f["call_size_mismatch_field"] == 0
    assert f["call_flag_sizeof_non_dst"] == 0


def test_an_arrow_destination_is_not_recognised_as_a_field():
    """``p->field`` reads as a plain destination, unlike ``p.field``.

    The front end wraps the base of an arrow access in a PointerDereference, and
    the member reader only names a base that is a bare Identifier -- so all four
    field flags stay 0 here. Pinned as a known limitation, not an endorsement: it
    means a `memcpy(s->buf, src, sizeof(*s))` mismatch goes unflagged.
    """
    f = flags_for("memcpy", arrow("s", "buf"), ident("src"), expr("sizeof(*s)"))
    assert f["call_dst_is_field"] == 0
    assert f["call_size_is_sizeof_base_struct"] == 0
    assert f["call_size_mismatch_field"] == 0


# ---------------------------------------------------------------------------
# how the size is written
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "size,kind",
    [
        ("16", 1),  # integer literal
        ("n", 2),  # some other expression
        ("sizeof(dst)", 3),  # a bare sizeof
        ("sizeof(dst) - 1", 4),  # sizeof inside arithmetic
    ],
)
def test_size_kind_describes_how_the_size_was_written(size, kind):
    assert flags_for("memcpy", ident("dst"), ident("src"), expr(size))["call_size_kind"] == kind


def test_a_call_with_no_size_slot_has_no_size_kind():
    assert flags_for("strcpy", ident("dst"), ident("src"))["call_size_kind"] == 0


def test_too_few_arguments_means_no_slots_are_trusted():
    """The table declares a minimum argument count; below it nothing is read."""
    assert flags_for("memcpy", ident("dst"), ident("src"))["call_size_kind"] == 0


# ---------------------------------------------------------------------------
# name-based flags
# ---------------------------------------------------------------------------


def test_the_unbounded_family_is_flagged_by_name():
    assert flags_for("strcpy", ident("dst"), ident("src"))["call_flag_danger_unbounded"] == 1
    assert flags_for("memcpy", ident("dst"), ident("src"), expr("n"))["call_flag_danger_unbounded"] == 0


def test_the_printf_family_is_flagged_as_variadic():
    assert flags_for("sprintf", ident("dst"), expr('"%s"'), ident("src"))["call_flag_has_varargs"] == 1
    assert flags_for("memcpy", ident("dst"), ident("src"), expr("n"))["call_flag_has_varargs"] == 0


def test_an_allocation_says_whether_its_size_mentions_sizeof():
    """1 means allocated without sizeof, 2 with; 0 means not an allocation."""
    assert flags_for("malloc", expr("sizeof(struct S) * n"))["alloc_sizeof_state"] == 2
    assert flags_for("malloc", expr("n"))["alloc_sizeof_state"] == 1
    assert flags_for("memcpy", ident("dst"), ident("src"), expr("n"))["alloc_sizeof_state"] == 0


def test_without_a_call_ast_only_the_name_based_flags_are_set():
    """This path used to raise AttributeError, reaching for a fallback that had
    been lost in the TypeScript migration."""
    extractor = ASTExtractor({"nodeType": "FunctionDefinition", "name": "f", "children": []})
    f = extractor.compute_call_flags(fname="strcpy", call_ast=None, code="strcpy(a, b)")
    assert f["call_flag_danger_unbounded"] == 1
    assert f["call_size_kind"] == 0
    assert f["call_flag_len_linked_to_dst"] == 0
