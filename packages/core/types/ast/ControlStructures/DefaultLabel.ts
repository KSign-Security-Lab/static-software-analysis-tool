import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IDefaultLabel extends IBaseNode {
  nodeType: ASTNodeTypes.DefaultLabel;
}
