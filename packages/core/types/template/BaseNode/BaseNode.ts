// Re-export types from BaseTypes to maintain backward compatibility
export { ExtractNodeType, IBaseNode, isDeclaration, isExpression, isNodeType, isStatement, NodeWithType, TemplateNodeTypes } from "./BaseTypes.ts";

// Re-export utility types
export type {
  DataTypeNodes,
  DeclarationNodes,
  DeepMapNodeProperties,
  ExpressionNodes,
  ExtractNodeTypes,
  FilterByNodeType,
  FilterByNodeTypes,
  FindNodesMatching,
  FindNodesOfType,
  FindNodesWithPropertyValue,
  HasChildOfType,
  HasChildren,
  HasProperty,
  HasPropertyOfType,
  IsLeaf,
  MapNodeProperties,
  NamedNodes,
  NodeChildren,
  NodeDescendants,
  NodeParent,
  OmitNodeProperties,
  OperatorNodes,
  PartialNode,
  PickNodeProperties,
  RequiredNode,
  StatementNodes,
  TypedNodes,
} from "./UtilityTypes.ts";
