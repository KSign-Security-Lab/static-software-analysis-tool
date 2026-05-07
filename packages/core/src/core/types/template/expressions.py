"""Expression node type definitions."""

from typing import Optional

from pydantic import BaseModel

from .BaseNode.base_types import IBaseNode, TemplateNodeTypes


class IAddressOfExpression(IBaseNode):
    """Address-of expression node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.AddressOfExpression
    type: str


class IArraySizeAllocation(IBaseNode):
    """Array size allocation node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.ArraySizeAllocation
    length: int | str


class IArraySubscriptExpression(IBaseNode):
    """Array subscript expression node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.ArraySubscriptExpression


class IAssignmentExpression(IBaseNode):
    """Assignment expression node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.AssignmentExpression
    operator: str


class IBinaryExpression(IBaseNode):
    """Binary expression node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.BinaryExpression
    operator: str
    type: str


class ICastExpression(IBaseNode):
    """Cast expression node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.CastExpression
    targetType: str


class IIdentifier(IBaseNode):
    """Identifier node."""

    name: str
    nodeType: TemplateNodeTypes = TemplateNodeTypes.Identifier
    size: Optional[str] = None
    type: str


class ILiteral(IBaseNode):
    """Literal node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.Literal
    type: str
    size: Optional[int] = None
    value: str


class IMemberAccess(IBaseNode):
    """Member access node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.MemberAccess
    type: str


class IPointerDereference(IBaseNode):
    """Pointer dereference node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.PointerDereference


class ISizeOfExpression(IBaseNode):
    """Sizeof expression node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.SizeOfExpression


class IStandardLibCall(IBaseNode):
    """Standard library call node."""

    name: str
    nodeType: TemplateNodeTypes = TemplateNodeTypes.StandardLibCall


class IUnaryExpression(IBaseNode):
    """Unary expression node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.UnaryExpression
    operator: str
    type: str


class IUserDefinedCall(IBaseNode):
    """User-defined call node."""

    nodeType: TemplateNodeTypes = TemplateNodeTypes.UserDefinedCall


