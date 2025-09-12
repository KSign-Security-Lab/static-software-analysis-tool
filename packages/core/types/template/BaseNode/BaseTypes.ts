/**
 * Base types and enums for template nodes
 * This file contains the fundamental types that other files can import without circular dependencies
 */

export enum TemplateNodeTypes {
  AddressOfExpression = "AddressOfExpression",
  ArrayDeclaration = "ArrayDeclaration",
  ArraySizeAllocation = "ArraySizeAllocation",
  ArraySubscriptExpression = "ArraySubscriptExpression",
  AssignmentExpression = "AssignmentExpression",
  BinaryExpression = "BinaryExpression",
  BreakStatement = "BreakStatement",
  CaseLabel = "CaseLabel",
  CastExpression = "CastExpression",
  CompoundStatement = "CompoundStatement",
  ContinueStatement = "ContinueStatement",
  DefaultLabel = "DefaultLabel",
  DoWhileStatement = "DoWhileStatement",
  EnumType = "EnumType",
  ForStatement = "ForStatement",
  FunctionDeclaration = "FunctionDeclaration",
  FunctionDefinition = "FunctionDefinition",
  GotoStatement = "GotoStatement",
  Identifier = "Identifier",
  IfStatement = "IfStatement",
  IncludeDirective = "IncludeDirective",
  Label = "Label",
  Literal = "Literal",
  MacroDefinition = "MacroDefinition",
  MemberAccess = "MemberAccess",
  ParameterDeclaration = "ParameterDeclaration",
  ParameterList = "ParameterList",
  PointerDeclaration = "PointerDeclaration",
  PointerDereference = "PointerDereference",
  ReturnStatement = "ReturnStatement",
  SizeOfExpression = "SizeOfExpression",
  StandardLibCall = "StandardLibCall",
  StructType = "StructType",
  SwitchStatement = "SwitchStatement",
  TranslationUnit = "TranslationUnit",
  TypeDefinition = "TypeDefinition",
  UnaryExpression = "UnaryExpression",
  UnionType = "UnionType",
  UserDefinedCall = "UserDefinedCall",
  VariableDeclaration = "VariableDeclaration",
  WhileStatement = "WhileStatement",
}

/**
 * Base interface that all template nodes must extend
 */
export interface IBaseNode {
  /** Unique identifier for the node */
  id: number;
  /** Type of the node */
  nodeType: TemplateNodeTypes;
  /** Optional source code representation */
  code?: string;
  /** Optional child nodes */
  children?: IBaseNode[];
  /** Optional name property for nodes that have names */
  name?: string;
  /** Optional type property for nodes that have types */
  type?: string;
  /** Optional size property for nodes that have sizes */
  size?: string | number;
  /** Optional length property for nodes that have lengths */
  length?: number | string;
  /** Optional level property for nodes that have levels */
  level?: number;
  /** Optional storage property for nodes that have storage */
  storage?: string;
}

/**
 * Utility type to extract node type from a node interface
 */
export type ExtractNodeType<T> = T extends { nodeType: infer U } ? U : never;

/**
 * Utility type to create a node with a specific type
 */
export type NodeWithType<T extends TemplateNodeTypes> = IBaseNode & {
  nodeType: T;
};

/**
 * Type guard to check if a node has a specific type
 */
export function isNodeType<T extends TemplateNodeTypes>(node: IBaseNode, nodeType: T): node is NodeWithType<T> {
  return node.nodeType === nodeType;
}

/**
 * Type guard to check if a node is a statement
 */
export function isStatement(node: IBaseNode): boolean {
  const statementTypes = [
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
  ];
  return statementTypes.includes(node.nodeType);
}

/**
 * Type guard to check if a node is an expression
 */
export function isExpression(node: IBaseNode): boolean {
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
 * Type guard to check if a node is a declaration
 */
export function isDeclaration(node: IBaseNode): boolean {
  const declarationTypes = [
    TemplateNodeTypes.ArrayDeclaration,
    TemplateNodeTypes.FunctionDeclaration,
    TemplateNodeTypes.FunctionDefinition,
    TemplateNodeTypes.ParameterDeclaration,
    TemplateNodeTypes.PointerDeclaration,
    TemplateNodeTypes.VariableDeclaration,
  ];
  return declarationTypes.includes(node.nodeType);
}
