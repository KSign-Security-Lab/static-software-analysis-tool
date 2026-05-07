"""Data type node definitions."""

from .BaseNode.base_types import IBaseNode, TemplateNodeTypes


class IEnumType(IBaseNode):
    """Enum type node."""

    name: str
    nodeType: TemplateNodeTypes = TemplateNodeTypes.EnumType


class IStructType(IBaseNode):
    """Struct type node."""

    name: str
    nodeType: TemplateNodeTypes = TemplateNodeTypes.StructType


class ITypeDefinition(IBaseNode):
    """Type definition node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.TypeDefinition
    name: str
    underlyingType: str


class IUnionType(IBaseNode):
    """Union type node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.UnionType
    name: str


