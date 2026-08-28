"""Template type definitions."""

from typing import Dict, List, TypedDict

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


class TemplateFlattenedGraph(TypedDict):
    """A flattened template: the same nodes, plus explicit parent/child edges.

    ``nodes`` holds the original template nodes -- flattening collects and sorts
    them, it does not reshape them. There used to be a separate
    ``TemplateFlattenedNode`` stub here declaring only ``id`` and ``nodeType``
    with a "... other fields from IBaseNode" comment; nothing referenced it.
    """

    edges: List[Dict[str, int]]  # { from: int, to: int }
    nodes: List["TemplateNodes"]


__all__ = [
    "TemplateNodeTypes",
    "IBaseNode",
    "TemplateNodes",
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
