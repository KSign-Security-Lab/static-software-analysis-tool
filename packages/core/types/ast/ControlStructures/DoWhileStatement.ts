import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IDoWhileStatement extends IBaseNode {
  nodeType: ASTNodeTypes.DoWhileStatement;
}
