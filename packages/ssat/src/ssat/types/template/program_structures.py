from typing import Required

from .BaseNode.base_types import IBaseNode


class IArrayDeclaration(IBaseNode):
    elementType: str


class IFunctionDeclaration(IBaseNode):
    pass


class IFunctionDefinition(IBaseNode):
    returnType: Required[str]


class IParameterDeclaration(IBaseNode):
    pass


class IParameterList(IBaseNode):
    pass


class IPointerDeclaration(IBaseNode):
    pointingType: str


class ITranslationUnit(IBaseNode):
    pass


class IVariableDeclaration(IBaseNode):
    pass
