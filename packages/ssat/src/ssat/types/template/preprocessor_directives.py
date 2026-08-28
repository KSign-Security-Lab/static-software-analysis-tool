"""Preprocessor directive node type definitions."""

from .BaseNode.base_types import IBaseNode


class IIncludeDirective(IBaseNode):
    """Include directive node."""


class IMacroDefinition(IBaseNode):
    """Macro definition node."""
