import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface ICaseLabel extends IBaseNode {
  nodeType: ASTNodeTypes.CaseLabel;
}
