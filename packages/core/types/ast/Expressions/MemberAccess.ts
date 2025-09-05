import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IMemberAccess extends IBaseNode {
  nodeType: ASTNodeTypes.MemberAccess;
  type: string;
}
