import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface ICastExpression extends IBaseNode {
  nodeType: ASTNodeTypes.CastExpression;
  targetType: string;
}
