import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IReturnStatement extends IBaseNode {
  nodeType: ASTNodeTypes.ReturnStatement;
}
