import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IContinueStatement extends IBaseNode {
  nodeType: ASTNodeTypes.ContinueStatement;
}
