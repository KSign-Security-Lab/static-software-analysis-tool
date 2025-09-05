import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IUnaryExpression extends IBaseNode {
  nodeType: ASTNodeTypes.UnaryExpression;
  operator: string;
  type: string;
}
