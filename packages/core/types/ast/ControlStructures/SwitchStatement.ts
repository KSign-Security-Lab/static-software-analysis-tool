import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface ISwitchStatement extends IBaseNode {
  nodeType: ASTNodeTypes.SwitchStatement;
}
