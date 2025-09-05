import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IStandardLibCall extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.StandardLibCall;
}
