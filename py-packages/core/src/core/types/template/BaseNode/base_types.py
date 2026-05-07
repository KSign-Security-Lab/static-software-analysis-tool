"""Base types and enums for template nodes."""

from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel


class TemplateNodeTypes(str, Enum):
    """Enumeration of all template node types."""

    AddressOfExpression = "AddressOfExpression"
    ArrayDeclaration = "ArrayDeclaration"
    ArraySizeAllocation = "ArraySizeAllocation"
    ArraySubscriptExpression = "ArraySubscriptExpression"
    AssignmentExpression = "AssignmentExpression"
    BinaryExpression = "BinaryExpression"
    BreakStatement = "BreakStatement"
    CaseLabel = "CaseLabel"
    CastExpression = "CastExpression"
    CompoundStatement = "CompoundStatement"
    ContinueStatement = "ContinueStatement"
    DefaultLabel = "DefaultLabel"
    DoWhileStatement = "DoWhileStatement"
    EnumType = "EnumType"
    ForStatement = "ForStatement"
    FunctionDeclaration = "FunctionDeclaration"
    FunctionDefinition = "FunctionDefinition"
    GotoStatement = "GotoStatement"
    Identifier = "Identifier"
    IfStatement = "IfStatement"
    IncludeDirective = "IncludeDirective"
    Label = "Label"
    Literal = "Literal"
    MacroDefinition = "MacroDefinition"
    MemberAccess = "MemberAccess"
    ParameterDeclaration = "ParameterDeclaration"
    ParameterList = "ParameterList"
    PointerDeclaration = "PointerDeclaration"
    PointerDereference = "PointerDereference"
    ReturnStatement = "ReturnStatement"
    SizeOfExpression = "SizeOfExpression"
    StandardLibCall = "StandardLibCall"
    StructType = "StructType"
    SwitchStatement = "SwitchStatement"
    TranslationUnit = "TranslationUnit"
    TypeDefinition = "TypeDefinition"
    UnaryExpression = "UnaryExpression"
    UnionType = "UnionType"
    UserDefinedCall = "UserDefinedCall"
    VariableDeclaration = "VariableDeclaration"
    WhileStatement = "WhileStatement"


class IBaseNode(BaseModel):
    """Base interface that all template nodes must extend."""

    id: int
    nodeType: TemplateNodeTypes
    code: Optional[str] = None
    children: Optional[List["IBaseNode"]] = None
    name: Optional[str] = None
    type: Optional[str] = None
    size: Optional[Union[str, int]] = None
    length: Optional[Union[int, str]] = None
    level: Optional[int] = None
    storage: Optional[str] = None

    class Config:
        """Pydantic configuration."""

        use_enum_values = True


def is_node_type(node: IBaseNode, node_type: TemplateNodeTypes) -> bool:
    """Type guard to check if a node has a specific type."""
    return node.nodeType == node_type


def is_statement(node: IBaseNode) -> bool:
    """Type guard to check if a node is a statement."""
    statement_types = [
        TemplateNodeTypes.CompoundStatement,
        TemplateNodeTypes.BreakStatement,
        TemplateNodeTypes.ContinueStatement,
        TemplateNodeTypes.DoWhileStatement,
        TemplateNodeTypes.ForStatement,
        TemplateNodeTypes.GotoStatement,
        TemplateNodeTypes.IfStatement,
        TemplateNodeTypes.ReturnStatement,
        TemplateNodeTypes.SwitchStatement,
        TemplateNodeTypes.WhileStatement,
    ]
    return node.nodeType in statement_types


def is_expression(node: IBaseNode) -> bool:
    """Type guard to check if a node is an expression."""
    expression_types = [
        TemplateNodeTypes.AddressOfExpression,
        TemplateNodeTypes.ArraySizeAllocation,
        TemplateNodeTypes.ArraySubscriptExpression,
        TemplateNodeTypes.AssignmentExpression,
        TemplateNodeTypes.BinaryExpression,
        TemplateNodeTypes.CastExpression,
        TemplateNodeTypes.Identifier,
        TemplateNodeTypes.Literal,
        TemplateNodeTypes.MemberAccess,
        TemplateNodeTypes.PointerDereference,
        TemplateNodeTypes.SizeOfExpression,
        TemplateNodeTypes.StandardLibCall,
        TemplateNodeTypes.UnaryExpression,
        TemplateNodeTypes.UserDefinedCall,
    ]
    return node.nodeType in expression_types


def is_declaration(node: IBaseNode) -> bool:
    """Type guard to check if a node is a declaration."""
    declaration_types = [
        TemplateNodeTypes.ArrayDeclaration,
        TemplateNodeTypes.FunctionDeclaration,
        TemplateNodeTypes.FunctionDefinition,
        TemplateNodeTypes.ParameterDeclaration,
        TemplateNodeTypes.PointerDeclaration,
        TemplateNodeTypes.VariableDeclaration,
    ]
    return node.nodeType in declaration_types


