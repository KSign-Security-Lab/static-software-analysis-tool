import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IUnionType extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.UnionType;
}
