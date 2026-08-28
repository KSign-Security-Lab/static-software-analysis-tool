"""Expression node type definitions."""

from typing import Required


from .BaseNode.base_types import IBaseNode


class IAddressOfExpression(IBaseNode):
    """Address-of expression node."""


class IArraySizeAllocation(IBaseNode):
    """Array size allocation node."""


class IArraySubscriptExpression(IBaseNode):
    """Array subscript expression node."""


class IAssignmentExpression(IBaseNode):
    """Assignment expression node."""

    operator: Required[str]


class IBinaryExpression(IBaseNode):
    """Binary expression node."""

    operator: str


class ICastExpression(IBaseNode):
    """Cast expression node."""

    targetType: Required[str]


class IIdentifier(IBaseNode):
    """Identifier node."""


class ILiteral(IBaseNode):
    """Literal node."""

    value: Required[str]


class IMemberAccess(IBaseNode):
    """Member access node."""


class IPointerDereference(IBaseNode):
    """Pointer dereference node."""


class ISizeOfExpression(IBaseNode):
    """Sizeof expression node."""


class IStandardLibCall(IBaseNode):
    """Standard library call node."""


class IUnaryExpression(IBaseNode):
    """Unary expression node."""

    operator: str


class IUserDefinedCall(IBaseNode):
    """User-defined call node."""
