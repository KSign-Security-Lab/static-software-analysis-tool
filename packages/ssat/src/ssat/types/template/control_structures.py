from typing import Required

from .BaseNode.base_types import IBaseNode


class IBreakStatement(IBaseNode):
    pass


class ICaseLabel(IBaseNode):
    pass


class IContinueStatement(IBaseNode):
    pass


class IDefaultLabel(IBaseNode):
    pass


class IDoWhileStatement(IBaseNode):
    pass


class IForStatement(IBaseNode):
    pass


class IGotoStatement(IBaseNode):
    jumpTarget: Required[str]


class IIfStatement(IBaseNode):
    pass


class ILabel(IBaseNode):
    pass


class IReturnStatement(IBaseNode):
    pass


class ISwitchStatement(IBaseNode):
    pass


class IWhileStatement(IBaseNode):
    pass
