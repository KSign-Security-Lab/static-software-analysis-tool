from enum import Enum
from typing import List, Optional, Required, TypedDict, Union


class TemplateNodeTypes(str, Enum):
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
    UNKNOWN = "UNKNOWN"
    IDENTIFIER = "IDENTIFIER"
    LOCAL = "LOCAL"
    MEMBER = "MEMBER"
    METHOD = "METHOD"
    METHOD_PARAMETER_IN = "METHOD_PARAMETER_IN"
    METHOD_PARAMETER_OUT = "METHOD_PARAMETER_OUT"
    METHOD_RETURN = "METHOD_RETURN"
    PARAM = "PARAM"
    BLOCK = "BLOCK"
    CALL = "CALL"
    CONTROL_STRUCTURE = "CONTROL_STRUCTURE"
    FIELD_IDENTIFIER = "FIELD_IDENTIFIER"
    FILE = "FILE"
    IMPORT = "IMPORT"
    JUMP_TARGET = "JUMP_TARGET"
    METHOD_REF = "METHOD_REF"
    MODIFIER = "MODIFIER"
    NAMESPACE = "NAMESPACE"
    NAMESPACE_BLOCK = "NAMESPACE_BLOCK"
    RETURN = "RETURN"
    TYPE = "TYPE"
    TYPE_DECL = "TYPE_DECL"
    TYPE_REF = "TYPE_REF"


class IBaseNode(TypedDict, total=False):
    id: Required[int]
    nodeType: Required[TemplateNodeTypes]
    code: Optional[str]
    children: Optional[List["IBaseNode"]]
    name: Optional[str]
    type: Optional[str]
    size: Optional[Union[str, int]]
    length: Optional[Union[int, str]]
    level: Optional[int]
    storage: Optional[str]


def is_node_type(node: IBaseNode, node_type: TemplateNodeTypes) -> bool:
    return node.get("nodeType") == node_type


def is_statement(node: IBaseNode) -> bool:
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
    return node.get("nodeType") in statement_types


def is_expression(node: IBaseNode) -> bool:
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
    return node.get("nodeType") in expression_types


def is_declaration(node: IBaseNode) -> bool:
    declaration_types = [
        TemplateNodeTypes.ArrayDeclaration,
        TemplateNodeTypes.FunctionDeclaration,
        TemplateNodeTypes.FunctionDefinition,
        TemplateNodeTypes.ParameterDeclaration,
        TemplateNodeTypes.PointerDeclaration,
        TemplateNodeTypes.VariableDeclaration,
    ]
    return node.get("nodeType") in declaration_types
