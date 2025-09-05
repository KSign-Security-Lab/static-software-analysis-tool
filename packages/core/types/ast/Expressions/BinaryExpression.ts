import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IBinaryExpression extends IBaseNode {
  nodeType: ASTNodeTypes.BinaryExpression;
  operator: string;
  type: string;
}
