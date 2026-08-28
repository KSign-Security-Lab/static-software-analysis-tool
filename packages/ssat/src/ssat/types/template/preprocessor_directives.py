"""Preprocessor directive node type definitions."""

from .BaseNode.base_types import IBaseNode, TemplateNodeTypes


class IIncludeDirective(IBaseNode):
    """Include directive node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.IncludeDirective
    name: str


class IMacroDefinition(IBaseNode):
    """Macro definition node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.MacroDefinition


