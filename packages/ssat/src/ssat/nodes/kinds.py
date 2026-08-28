"""Node-type sets shared by the passes that walk a Template AST.

Only genuinely shared sets belong here. Notably absent is ``CONTROL_NODES``: the
AST pass counts four control structures and the DFG pass counts six (it also
treats ``DoStatement`` and ``DoWhileStatement`` as control). Hoisting that one
would silently change whichever pass lost its own definition, so each keeps it.
"""

from __future__ import annotations

#: Nodes that represent a call, whatever the front end resolved it to.
CALL_NODE_TYPES = frozenset({"CallExpression", "StandardLibCall", "UserDefinedCall"})

#: Call nodes a statement can consist of entirely.
STATEMENT_CALL_NODE_TYPES = frozenset({"StandardLibCall", "UserDefinedCall"})

#: Argument-list wrappers; a statement-level call sometimes points only at one.
ARGLIST_NODE_TYPES = frozenset({"ParameterList", "ArgumentList"})

#: Declarations that introduce exactly one named variable.
SIMPLE_DECL_NODE_TYPES = frozenset({"VariableDeclaration", "ParameterDeclaration", "PointerDeclaration"})

#: Declarations that reserve storage with a length.
ARRAY_DECL_NODE_TYPES = frozenset({"ArrayDeclaration", "ArraySizeAllocation"})

#: Left-hand sides that write *into* a container rather than replacing it.
CONTAINER_WRITE_NODE_TYPES = frozenset({"ArraySubscriptExpression", "MemberAccess"})


# ---------------------------------------------------------------------------
# Guard-edge vocabulary. The AST pass writes these onto guard edges and the DFG
# pass reads them back, so the two must agree -- hence one definition.
# ---------------------------------------------------------------------------

GUARD_KIND_IF = 1
GUARD_KIND_LOOP = 2
GUARD_KIND_SWITCH = 4
GUARD_KINDS = frozenset({GUARD_KIND_IF, GUARD_KIND_LOOP, GUARD_KIND_SWITCH})

#: guard_branch values for an if edge.
IF_THEN_BRANCH = 0
IF_ELSE_BRANCH = 1
#: guard_branch value for a loop body edge.
LOOP_BODY_BRANCH = 2
