"""Readers for the Template AST node dicts the extractors walk.

:mod:`ssat.ast.extractor` and :mod:`ssat.dfg.extractor` consume the same node
shape -- ``{"nodeType", "children", "code", "name", "operator", "value"}`` -- and
each used to carry its own copy of every reader here. The copies had already
drifted: two 180-line guard analysers that were meant to agree, and two
``fullname_from_expr`` differing only in how they peel casts.

Where the copies genuinely disagreed the difference is now a parameter rather
than a silent choice, so each extractor keeps the behaviour it had. See
:func:`ssat.nodes.expr.fullname_from_expr` and
:func:`ssat.nodes.guards.int_from_literal_node`.
"""

from .expr import (
    fullname_from_expr as fullname_from_expr,
    is_member_access as is_member_access,
    member_parts as member_parts,
    unwrap_ast as unwrap_ast,
    unwrap_cast_paren as unwrap_cast_paren,
    unwrap_cast_typeref as unwrap_cast_typeref,
)
from .guards import (
    guards_from_condition_ast as guards_from_condition_ast,
    guards_from_for_header as guards_from_for_header,
    ident_name as ident_name,
    int_from_literal_node as int_from_literal_node,
    int_from_node as int_from_node,
    is_int_literal as is_int_literal,
    norm_val as norm_val,
)
