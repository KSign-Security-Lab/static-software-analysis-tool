import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IArrayDeclaration extends IBaseNode {
  elementType: string;
  length: number | string;
  name: string;
  nodeType: ASTNodeTypes.ArrayDeclaration;
  storage?: string;
}
