import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IIdentifier extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.Identifier;
  size?: string;
  type: string;
}
