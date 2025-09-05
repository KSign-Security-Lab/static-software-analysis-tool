import { CallVertexProperties, TreeNode } from "../types/cpg";
import { BinaryExpressionBooleanMap } from "./config/BinaryExpression";

/**
 * Given a TreeNode for a call/operator, pick its result type.
 * 1) hard-coded boolean map for known binary operators
 * 2) raw TYPE_FULL_NAME if present
 * 3) bottom-up inference from children
 * 4) fallback to "<unknown>"
 */
export function BinaryUnaryTypeWrapper(node: TreeNode): string {
  // 1) boolean-map override
  const boolType = BinaryExpressionBooleanMap[node.name];
  if (boolType) {
    return boolType;
  }

  // 2) trust TYPE_FULL_NAME shape
  const props = node.properties as unknown as CallVertexProperties;
  const rawList = props.TYPE_FULL_NAME["@value"]["@value"];
  if (rawList.length > 0) {
    return rawList.join("/");
  }

  // 3) infer from children
  const childrenTypes = node.children.map(inferTypeBottomUp);
  const unique = new Set(childrenTypes);
  if (unique.size === 1) {
    return [...unique][0];
  }

  // 4) give up
  return "<unknown>";
}

/**
 * Recursively infer type by merging its children’s types.
 */
export function inferTypeBottomUp(node: TreeNode): string {
  if (node.children.length === 0) {
    return "unknown";
  }
  const childTypes = node.children.map(inferTypeBottomUp);
  const unique = Array.from(new Set(childTypes));
  if (unique.length === 1) {
    return unique[0];
  }
  return `(${unique.join(" ")})`;
}
