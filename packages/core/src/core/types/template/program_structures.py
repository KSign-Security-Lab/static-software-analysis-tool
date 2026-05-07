"""Program structure node type definitions."""

from typing import Optional

from .BaseNode.base_types import IBaseNode, TemplateNodeTypes


class IArrayDeclaration(IBaseNode):
    """Array declaration node."""

    elementType: str
    length: int | str
    name: str
    nodeType: TemplateNodeTypes = TemplateNodeTypes.ArrayDeclaration
    storage: Optional[str] = None


class IFunctionDeclaration(IBaseNode):
    """Function declaration node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.FunctionDeclaration


class IFunctionDefinition(IBaseNode):
    """Function definition node."""

    name: str
    nodeType: TemplateNodeTypes = TemplateNodeTypes.FunctionDefinition
    returnType: str


class IParameterDeclaration(IBaseNode):
    """Parameter declaration node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.ParameterDeclaration
    name: str
    type: str
    size: Optional[str] = None


class IParameterList(IBaseNode):
    """Parameter list node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.ParameterList


class IPointerDeclaration(IBaseNode):
    """Pointer declaration node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.PointerDeclaration
    name: str
    pointingType: str
    level: int


class ITranslationUnit(IBaseNode):
    """Translation unit node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.TranslationUnit


class IVariableDeclaration(IBaseNode):
    """Variable declaration node."""

    name: str
    nodeType: TemplateNodeTypes = TemplateNodeTypes.VariableDeclaration
    storage: Optional[str] = None
    type: str


