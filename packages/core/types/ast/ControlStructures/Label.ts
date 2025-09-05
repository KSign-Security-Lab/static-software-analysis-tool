import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface ILabel extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.Label;
}
