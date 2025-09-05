import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IBreakStatement extends IBaseNode {
  nodeType: ASTNodeTypes.BreakStatement;
}
