"""Control structure node type definitions."""

from typing import Required

from .BaseNode.base_types import IBaseNode


class IBreakStatement(IBaseNode):
    """Break statement node."""


class ICaseLabel(IBaseNode):
    """Case label node."""


class IContinueStatement(IBaseNode):
    """Continue statement node."""


class IDefaultLabel(IBaseNode):
    """Default label node."""


class IDoWhileStatement(IBaseNode):
    """Do-while statement node."""


class IForStatement(IBaseNode):
    """For statement node."""


class IGotoStatement(IBaseNode):
    """Goto statement node."""

    jumpTarget: Required[str]


class IIfStatement(IBaseNode):
    """If statement node."""


class ILabel(IBaseNode):
    """Label node."""


class IReturnStatement(IBaseNode):
    """Return statement node."""


class ISwitchStatement(IBaseNode):
    """Switch statement node."""


class IWhileStatement(IBaseNode):
    """While statement node."""
