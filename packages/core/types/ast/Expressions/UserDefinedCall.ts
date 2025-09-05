import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IUserDefinedCall extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.UserDefinedCall;
}
