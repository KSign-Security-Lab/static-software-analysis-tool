// ============================================================================
// TYPES INDEX
// ============================================================================
// This file provides clean, consolidated imports for all types

// CPG types
export * from "./cpg";

// DFG types
export * from "./dfg";

// Main node types
export * from "./node";

// Re-export commonly used types for convenience
export type { IBaseNode, TemplateFlattenedGraph, TemplateFlattenedNode, TemplateNodes, TemplateNodeTypes } from "./node";

// Template types (consolidated) - excluding conflicting exports
export {
  // Re-export specific types to avoid conflicts
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
