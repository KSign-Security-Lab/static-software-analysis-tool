"""Data type node definitions."""

from typing import Required

from .BaseNode.base_types import IBaseNode


class IEnumType(IBaseNode):
    """Enum type node."""


class IStructType(IBaseNode):
    """Struct type node."""


class ITypeDefinition(IBaseNode):
    """Type definition node."""

    underlyingType: Required[str]


class IUnionType(IBaseNode):
    """Union type node."""
