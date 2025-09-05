import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IAssignmentExpression extends IBaseNode {
  nodeType: ASTNodeTypes.AssignmentExpression;
  operator: string;
}
