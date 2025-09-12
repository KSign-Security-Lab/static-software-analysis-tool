import { TemplateNodes } from "../../node";
import { IBaseNode, TemplateNodeTypes } from "./BaseTypes";

/**
 * Utility types for better type manipulation and type safety
 */

// ============================================================================
// NODE FILTERING TYPES
// ============================================================================

/**
 * Filter nodes by a specific node type
 */
export type FilterByNodeType<T extends TemplateNodeTypes> = Extract<TemplateNodes, { nodeType: T }>;

/**
 * Filter nodes by multiple node types
 */
export type FilterByNodeTypes<T extends TemplateNodeTypes[]> = Extract<TemplateNodes, { nodeType: T[number] }>;

/**
 * Get all possible node types from a union of nodes
 */
export type ExtractNodeTypes<T> = T extends { nodeType: infer U } ? U : never;

// ============================================================================
// NODE PROPERTY EXTRACTION
// ============================================================================

/**
 * Extract nodes that have a specific property
 */
export type HasProperty<T extends keyof IBaseNode> = Extract<TemplateNodes, Record<T, unknown>>;

/**
 * Extract nodes that have a specific property with a specific type
 */
export type HasPropertyOfType<T extends keyof IBaseNode, U> = Extract<TemplateNodes, Record<T, U>>;

/**
 * Extract nodes that have a name property
 * Note: This works with specific node types that have name property
 */
export type NamedNodes = Extract<TemplateNodes, { name: string }>;

/**
 * Extract nodes that have a type property
 * Note: This works with specific node types that have type property
 */
export type TypedNodes = Extract<TemplateNodes, { type: string }>;

/**
 * Extract nodes that have an operator property
 * Note: This works with specific node types that have operator property
 */
export type OperatorNodes = Extract<TemplateNodes, { operator: string }>;

// ============================================================================
// NODE RELATIONSHIP TYPES
// ============================================================================

/**
 * Get the children of a node
 */
export type NodeChildren<T extends IBaseNode> = T["children"] extends (infer U)[] ? (U extends IBaseNode ? U : never) : never;

/**
 * Get the parent of a node (requires parent tracking)
 */
export type NodeParent<T extends IBaseNode> = T extends { parent?: infer U } ? (U extends IBaseNode ? U : never) : never;

/**
 * Get all descendants of a node (recursive)
 */
export type NodeDescendants<T extends IBaseNode> = T extends { children?: (infer U)[] }
  ? U extends IBaseNode
    ? U | NodeDescendants<U>
    : never
  : never;

// ============================================================================
// NODE VALIDATION TYPES
// ============================================================================

/**
 * Check if a node has children
 */
export type HasChildren<T extends IBaseNode> = T["children"] extends unknown[] ? (T["children"]["length"] extends 0 ? false : true) : false;

/**
 * Check if a node is a leaf (no children)
 */
export type IsLeaf<T extends IBaseNode> = T["children"] extends unknown[] ? (T["children"]["length"] extends 0 ? true : false) : true;

/**
 * Check if a node has a specific child type
 */
export type HasChildOfType<T extends IBaseNode, U extends TemplateNodeTypes> = T extends {
  children?: (infer C)[];
}
  ? C extends { nodeType: U }
    ? true
    : false
  : false;

// ============================================================================
// NODE TRANSFORMATION TYPES
// ============================================================================

/**
 * Make all properties of a node optional except id and nodeType
 */
export type PartialNode<T extends IBaseNode> = Partial<Omit<T, "id" | "nodeType">> & Pick<T, "id" | "nodeType">;

/**
 * Make all properties of a node required
 */
export type RequiredNode<T extends IBaseNode> = Required<T>;

/**
 * Create a node with only specific properties
 */
export type PickNodeProperties<T extends IBaseNode, K extends keyof T> = Pick<T, K>;

/**
 * Create a node without specific properties
 */
export type OmitNodeProperties<T extends IBaseNode, K extends keyof T> = Omit<T, K>;

// ============================================================================
// NODE QUERY TYPES
// ============================================================================

/**
 * Find nodes of a specific type in a tree
 */
export type FindNodesOfType<T extends TemplateNodeTypes> = Extract<TemplateNodes, { nodeType: T }>;

/**
 * Find nodes with a specific property value
 */
export type FindNodesWithPropertyValue<T extends keyof IBaseNode, U> = Extract<TemplateNodes, Record<T, U>>;

/**
 * Find nodes that match a predicate type
 */
export type FindNodesMatching<T> = Extract<TemplateNodes, T>;

// ============================================================================
// NODE OPERATION TYPES
// ============================================================================

/**
 * Map over node properties
 */
export type MapNodeProperties<T extends IBaseNode, U> = {
  [K in keyof T]: T[K] extends unknown[] ? U[] : U;
};

/**
 * Deep map over node properties (recursive)
 */
export type DeepMapNodeProperties<T, U> = T extends IBaseNode
  ? {
      [K in keyof T]: T[K] extends IBaseNode
        ? DeepMapNodeProperties<T[K], U>
        : T[K] extends IBaseNode[]
          ? DeepMapNodeProperties<T[K][number], U>[]
          : U;
    }
  : T;

// ============================================================================
// COMMON NODE TYPE UNIONS
// ============================================================================

/**
 * All statement node types
 */
export type StatementNodes = FilterByNodeTypes<
  [
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
>;

/**
 * All expression node types
 */
export type ExpressionNodes = FilterByNodeTypes<
  [
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
>;

/**
 * All declaration node types
 */
export type DeclarationNodes = FilterByNodeTypes<
  [
    TemplateNodeTypes.ArrayDeclaration,
    TemplateNodeTypes.FunctionDeclaration,
    TemplateNodeTypes.FunctionDefinition,
    TemplateNodeTypes.ParameterDeclaration,
    TemplateNodeTypes.PointerDeclaration,
    TemplateNodeTypes.VariableDeclaration,
  ]
>;

/**
 * All data type node types
 */
export type DataTypeNodes = FilterByNodeTypes<
  [TemplateNodeTypes.EnumType, TemplateNodeTypes.StructType, TemplateNodeTypes.TypeDefinition, TemplateNodeTypes.UnionType]
>;
