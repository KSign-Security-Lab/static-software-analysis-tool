import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IStructType extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.StructType;
}
