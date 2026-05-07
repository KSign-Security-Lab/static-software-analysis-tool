"""Block node type definitions."""

from .BaseNode.base_types import IBaseNode, TemplateNodeTypes


class ICompoundStatement(IBaseNode):
    """Compound statement node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.CompoundStatement


