import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface ISizeOfExpression extends IBaseNode {
  nodeType: ASTNodeTypes.SizeOfExpression;
}
