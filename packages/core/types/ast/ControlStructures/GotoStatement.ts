import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IGotoStatement extends IBaseNode {
  jumpTarget: string;
  nodeType: ASTNodeTypes.GotoStatement;
}
