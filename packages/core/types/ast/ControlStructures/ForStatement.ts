import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IForStatement extends IBaseNode {
  nodeType: ASTNodeTypes.ForStatement;
}
