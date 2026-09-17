from typing import Required


from .BaseNode.base_types import IBaseNode


class IAddressOfExpression(IBaseNode):
    pass


class IArraySizeAllocation(IBaseNode):
    pass


class IArraySubscriptExpression(IBaseNode):
    pass


class IAssignmentExpression(IBaseNode):
    operator: Required[str]


class IBinaryExpression(IBaseNode):
    operator: str


class ICastExpression(IBaseNode):
    targetType: Required[str]


class IIdentifier(IBaseNode):
    pass


class ILiteral(IBaseNode):
    value: Required[str]


class IMemberAccess(IBaseNode):
    pass


class IPointerDereference(IBaseNode):
    pass


class ISizeOfExpression(IBaseNode):
    pass


class IStandardLibCall(IBaseNode):
    pass


class IUnaryExpression(IBaseNode):
    operator: str


class IUserDefinedCall(IBaseNode):
    pass
