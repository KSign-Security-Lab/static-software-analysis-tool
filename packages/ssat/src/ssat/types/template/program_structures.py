"""Program structure node type definitions."""

from typing import Required

from .BaseNode.base_types import IBaseNode


class IArrayDeclaration(IBaseNode):
    """Array declaration node."""

    elementType: str


class IFunctionDeclaration(IBaseNode):
    """Function declaration node."""


class IFunctionDefinition(IBaseNode):
    """Function definition node."""

    returnType: Required[str]


class IParameterDeclaration(IBaseNode):
    """Parameter declaration node."""


class IParameterList(IBaseNode):
    """Parameter list node."""


class IPointerDeclaration(IBaseNode):
    """Pointer declaration node."""

    pointingType: str


class ITranslationUnit(IBaseNode):
    """Translation unit node."""


class IVariableDeclaration(IBaseNode):
    """Variable declaration node."""
