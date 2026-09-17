from __future__ import annotations

# Only genuinely shared sets. CONTROL_NODES stays private to each pass: the AST pass
# counts four control structures, the DFG pass six, and hoisting it would change one.

CALL_NODE_TYPES = frozenset({"CallExpression", "StandardLibCall", "UserDefinedCall"})
STATEMENT_CALL_NODE_TYPES = frozenset({"StandardLibCall", "UserDefinedCall"})
ARGLIST_NODE_TYPES = frozenset({"ParameterList", "ArgumentList"})
SIMPLE_DECL_NODE_TYPES = frozenset({"VariableDeclaration", "ParameterDeclaration", "PointerDeclaration"})
ARRAY_DECL_NODE_TYPES = frozenset({"ArrayDeclaration", "ArraySizeAllocation"})
CONTAINER_WRITE_NODE_TYPES = frozenset({"ArraySubscriptExpression", "MemberAccess"})


# Written by the AST pass onto guard edges and read back by the DFG pass, so the two
# must agree. Hence one definition.
GUARD_KIND_IF = 1
GUARD_KIND_LOOP = 2
GUARD_KIND_SWITCH = 4
GUARD_KINDS = frozenset({GUARD_KIND_IF, GUARD_KIND_LOOP, GUARD_KIND_SWITCH})
IF_THEN_BRANCH = 0
IF_ELSE_BRANCH = 1
LOOP_BODY_BRANCH = 2
