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

// Re-export commonly used types for convenience
export { IBaseNode, TemplateNodeTypes } from "./template/BaseNode/BaseTypes";
export type { ExtractNodeType, NodeWithType } from "./template/BaseNode/BaseTypes";
