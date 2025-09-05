import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IArraySubscriptExpression extends IBaseNode {
  nodeType: ASTNodeTypes.ArraySubscriptExpression;
}
