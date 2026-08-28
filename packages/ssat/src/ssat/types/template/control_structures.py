"""Control structure node type definitions."""

from .BaseNode.base_types import IBaseNode, TemplateNodeTypes


class IBreakStatement(IBaseNode):
    """Break statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.BreakStatement


class ICaseLabel(IBaseNode):
    """Case label node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.CaseLabel


class IContinueStatement(IBaseNode):
    """Continue statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.ContinueStatement


class IDefaultLabel(IBaseNode):
    """Default label node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.DefaultLabel


class IDoWhileStatement(IBaseNode):
    """Do-while statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.DoWhileStatement


class IForStatement(IBaseNode):
    """For statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.ForStatement


class IGotoStatement(IBaseNode):
    """Goto statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.GotoStatement
    jumpTarget: str


class IIfStatement(IBaseNode):
    """If statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.IfStatement


class ILabel(IBaseNode):
    """Label node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.Label
    name: str


class IReturnStatement(IBaseNode):
    """Return statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.ReturnStatement


class ISwitchStatement(IBaseNode):
    """Switch statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.SwitchStatement


class IWhileStatement(IBaseNode):
    """While statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.WhileStatement


