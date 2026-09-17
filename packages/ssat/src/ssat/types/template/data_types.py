from typing import Required

from .BaseNode.base_types import IBaseNode


class IEnumType(IBaseNode):
    pass


class IStructType(IBaseNode):
    pass


class ITypeDefinition(IBaseNode):
    underlyingType: Required[str]


class IUnionType(IBaseNode):
    pass
