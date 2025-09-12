// Import all node interfaces from consolidated files
import {
  IAddressOfExpression,
  IArrayDeclaration,
  IArraySizeAllocation,
  IArraySubscriptExpression,
  IAssignmentExpression,
  IBinaryExpression,
  IBreakStatement,
  ICaseLabel,
  ICastExpression,
  ICompoundStatement,
  IContinueStatement,
  IDefaultLabel,
  IDoWhileStatement,
  IEnumType,
  IForStatement,
  IFunctionDeclaration,
  IFunctionDefinition,
  IGotoStatement,
  IIdentifier,
  IIfStatement,
  IIncludeDirective,
  ILabel,
  ILiteral,
  IMacroDefinition,
  IMemberAccess,
  IParameterDeclaration,
  IParameterList,
  IPointerDeclaration,
  IPointerDereference,
  IReturnStatement,
  ISizeOfExpression,
  IStandardLibCall,
  IStructType,
  ISwitchStatement,
  ITranslationUnit,
  ITypeDefinition,
  IUnaryExpression,
  IUnionType,
  IUserDefinedCall,
  IVariableDeclaration,
  IWhileStatement,
} from "./template";
import { IBaseNode, TemplateNodeTypes } from "./template/BaseNode/BaseTypes";

/**
 * Union type of all possible template nodes
 * This is the main type that represents any node in the template AST
 */
export type TemplateNodes =
  | IBaseNode
  | TemplateBlockNodes
  | TemplateControlStructureNodes
  | TemplateDataTypesNodes
  | TemplateExpressionNodes
  | TemplatePreprocessorDirectiveNodes
  | TemplateProgramStructureNodes;

/**
 * A template node with a guaranteed unique ID
 * Used for flattened representations where every node has an ID
 */
export type TemplateFlattenedNode = TemplateNodes & { id: number };

/**
 * A graph representation of flattened template nodes
 * Contains nodes and edges between them
 */
export interface TemplateFlattenedGraph {
  /** Array of edges connecting nodes */
  edges: { from: number; to: number }[];
  /** Array of nodes in the graph */
  nodes: TemplateFlattenedNode[];
}

// ============================================================================
// NODE CATEGORIES
// ============================================================================

/**
 * Block-level nodes (compound statements, etc.)
 */
type TemplateBlockNodes = ICompoundStatement;

/**
 * Control structure nodes (if, for, while, switch, etc.)
 * Note: Data types have been moved to their own category
 */
type TemplateControlStructureNodes =
  | IBreakStatement
  | ICaseLabel
  | IContinueStatement
  | IDefaultLabel
  | IDoWhileStatement
  | IForStatement
  | IGotoStatement
  | IIfStatement
  | ILabel
  | IReturnStatement
  | ISwitchStatement
  | IWhileStatement;

/**
 * Data type nodes (structs, enums, unions, type definitions)
 * Moved from ControlStructures for better organization
 */
type TemplateDataTypesNodes = IEnumType | IStructType | ITypeDefinition | IUnionType;

/**
 * Expression nodes (binary, unary, calls, literals, etc.)
 */
type TemplateExpressionNodes =
  | IAddressOfExpression
  | IArraySizeAllocation
  | IArraySubscriptExpression
  | IAssignmentExpression
  | IBinaryExpression
  | ICastExpression
  | IIdentifier
  | ILiteral
  | IMemberAccess
  | IPointerDereference
  | ISizeOfExpression
  | IStandardLibCall
  | IUnaryExpression
  | IUserDefinedCall;

/**
 * Preprocessor directive nodes (includes, macros, etc.)
 */
type TemplatePreprocessorDirectiveNodes = IIncludeDirective | IMacroDefinition;

/**
 * Program structure nodes (functions, variables, parameters, etc.)
 */
type TemplateProgramStructureNodes =
  | IArrayDeclaration
  | IFunctionDeclaration
  | IFunctionDefinition
  | IParameterDeclaration
  | IParameterList
  | IPointerDeclaration
  | ITranslationUnit
  | IVariableDeclaration;

// ============================================================================
// UTILITY TYPES
// ============================================================================

/**
 * Extract the node type from a template node
 */
export type ExtractTemplateNodeType<T> = T extends { nodeType: infer U } ? U : never;

/**
 * Create a node type that extends IBaseNode with a specific nodeType
 */
export type TemplateNodeWithType<T extends TemplateNodeTypes> = IBaseNode & {
  nodeType: T;
};

/**
 * Type guard to check if a node is of a specific type
 */
export function isTemplateNodeType<T extends TemplateNodeTypes>(node: IBaseNode, nodeType: T): node is TemplateNodeWithType<T> {
  return node.nodeType === nodeType;
}

/**
 * Type guard to check if a node is a control structure
 */
export function isControlStructure(node: IBaseNode): node is TemplateControlStructureNodes {
  const controlTypes = [
    TemplateNodeTypes.BreakStatement,
    TemplateNodeTypes.CaseLabel,
    TemplateNodeTypes.ContinueStatement,
    TemplateNodeTypes.DefaultLabel,
    TemplateNodeTypes.DoWhileStatement,
    TemplateNodeTypes.ForStatement,
    TemplateNodeTypes.GotoStatement,
    TemplateNodeTypes.IfStatement,
    TemplateNodeTypes.Label,
    TemplateNodeTypes.ReturnStatement,
    TemplateNodeTypes.SwitchStatement,
    TemplateNodeTypes.WhileStatement,
  ];
  return controlTypes.includes(node.nodeType);
}

/**
 * Type guard to check if a node is a data type
 */
export function isDataType(node: IBaseNode): node is TemplateDataTypesNodes {
  const dataTypeTypes = [TemplateNodeTypes.EnumType, TemplateNodeTypes.StructType, TemplateNodeTypes.TypeDefinition, TemplateNodeTypes.UnionType];
  return dataTypeTypes.includes(node.nodeType);
}

/**
 * Type guard to check if a node is an expression
 */
export function isExpression(node: IBaseNode): node is TemplateExpressionNodes {
  const expressionTypes = [
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
  ];
  return expressionTypes.includes(node.nodeType);
}

/**
 * Type guard to check if a node is a program structure
 */
export function isProgramStructure(node: IBaseNode): node is TemplateProgramStructureNodes {
  const programStructureTypes = [
    TemplateNodeTypes.ArrayDeclaration,
    TemplateNodeTypes.FunctionDeclaration,
    TemplateNodeTypes.FunctionDefinition,
    TemplateNodeTypes.ParameterDeclaration,
    TemplateNodeTypes.ParameterList,
    TemplateNodeTypes.PointerDeclaration,
    TemplateNodeTypes.TranslationUnit,
    TemplateNodeTypes.VariableDeclaration,
  ];
  return programStructureTypes.includes(node.nodeType);
}

/**
 * Type guard to check if a node is a preprocessor directive
 */
export function isPreprocessorDirective(node: IBaseNode): node is TemplatePreprocessorDirectiveNodes {
  const preprocessorTypes = [TemplateNodeTypes.IncludeDirective, TemplateNodeTypes.MacroDefinition];
  return preprocessorTypes.includes(node.nodeType);
}

// ============================================================================
// RE-EXPORTS
// ============================================================================

// Re-export commonly used types for convenience
export { IBaseNode, TemplateNodeTypes } from "./template/BaseNode/BaseTypes";
export type { ExtractNodeType, NodeWithType } from "./template/BaseNode/BaseTypes";
