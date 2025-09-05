import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IIfStatement extends IBaseNode {
  nodeType: ASTNodeTypes.IfStatement;
}
