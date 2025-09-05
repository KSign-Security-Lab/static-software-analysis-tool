import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IWhileStatement extends IBaseNode {
  nodeType: ASTNodeTypes.WhileStatement;
}
