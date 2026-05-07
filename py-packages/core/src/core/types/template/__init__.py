"""Template type definitions."""

from typing import Union

from .BaseNode.base_types import IBaseNode, TemplateNodeTypes
from .blocks import ICompoundStatement
from .control_structures import (
    IBreakStatement,
    ICaseLabel,
    IContinueStatement,
    IDefaultLabel,
    IDoWhileStatement,
    IForStatement,
    IGotoStatement,
    IIfStatement,
    ILabel,
    IReturnStatement,
    ISwitchStatement,
    IWhileStatement,
)
from .data_types import IEnumType, IStructType, ITypeDefinition, IUnionType
from .expressions import (
    IAddressOfExpression,
    IArraySizeAllocation,
    IArraySubscriptExpression,
    IAssignmentExpression,
    IBinaryExpression,
    ICastExpression,
    IIdentifier,
    ILiteral,
    IMemberAccess,
    IPointerDereference,
    ISizeOfExpression,
    IStandardLibCall,
    IUnaryExpression,
    IUserDefinedCall,
)
from .preprocessor_directives import IIncludeDirective, IMacroDefinition
from .program_structures import (
    IArrayDeclaration,
    IFunctionDeclaration,
    IFunctionDefinition,
    IParameterDeclaration,
    IParameterList,
    IPointerDeclaration,
    ITranslationUnit,
    IVariableDeclaration,
)

# Union type of all possible template nodes
TemplateNodes = Union[
    IBaseNode,
    ICompoundStatement,
    IBreakStatement,
    ICaseLabel,
    IContinueStatement,
    IDefaultLabel,
    IDoWhileStatement,
    IForStatement,
    IGotoStatement,
    IIfStatement,
    ILabel,
    IReturnStatement,
    ISwitchStatement,
    IWhileStatement,
    IEnumType,
    IStructType,
    ITypeDefinition,
    IUnionType,
    IAddressOfExpression,
    IArraySizeAllocation,
    IArraySubscriptExpression,
    IAssignmentExpression,
    IBinaryExpression,
    ICastExpression,
    IIdentifier,
    ILiteral,
    IMemberAccess,
    IPointerDereference,
    ISizeOfExpression,
    IStandardLibCall,
    IUnaryExpression,
    IUserDefinedCall,
    IIncludeDirective,
    IMacroDefinition,
    IArrayDeclaration,
    IFunctionDeclaration,
    IFunctionDefinition,
    IParameterDeclaration,
    IParameterList,
    IPointerDeclaration,
    ITranslationUnit,
    IVariableDeclaration,
]

# Template flattened node and graph
from typing import List, TypedDict


class TemplateFlattenedNode(TypedDict):
    """A template node with a guaranteed unique ID."""

    id: int
    nodeType: str
    # ... other fields from IBaseNode


class TemplateFlattenedGraph(TypedDict):
    """A graph representation of flattened template nodes."""

    edges: List[dict]  # { from: int, to: int }
    nodes: List[TemplateFlattenedNode]


__all__ = [
    "TemplateNodeTypes",
    "IBaseNode",
    "TemplateNodes",
    "TemplateFlattenedNode",
    "TemplateFlattenedGraph",
    # Expressions
    "IAddressOfExpression",
    "IArraySizeAllocation",
    "IArraySubscriptExpression",
    "IAssignmentExpression",
    "IBinaryExpression",
    "ICastExpression",
    "IIdentifier",
    "ILiteral",
    "IMemberAccess",
    "IPointerDereference",
    "ISizeOfExpression",
    "IStandardLibCall",
    "IUnaryExpression",
    "IUserDefinedCall",
    # Blocks
    "ICompoundStatement",
    # Control structures
    "IBreakStatement",
    "ICaseLabel",
    "IContinueStatement",
    "IDefaultLabel",
    "IDoWhileStatement",
    "IForStatement",
    "IGotoStatement",
    "IIfStatement",
    "ILabel",
    "IReturnStatement",
    "ISwitchStatement",
    "IWhileStatement",
    # Data types
    "IEnumType",
    "IStructType",
    "ITypeDefinition",
    "IUnionType",
    # Preprocessor
    "IIncludeDirective",
    "IMacroDefinition",
    # Program structures
    "IArrayDeclaration",
    "IFunctionDeclaration",
    "IFunctionDefinition",
    "IParameterDeclaration",
    "IParameterList",
    "IPointerDeclaration",
    "ITranslationUnit",
    "IVariableDeclaration",
]


