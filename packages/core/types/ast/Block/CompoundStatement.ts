import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface ICompoundStatement extends IBaseNode {
  nodeType: ASTNodeTypes.CompoundStatement;
}
