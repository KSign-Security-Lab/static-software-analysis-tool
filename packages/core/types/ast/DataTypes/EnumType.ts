import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IEnumType extends IBaseNode {
  nodeType: ASTNodeTypes.EnumType;
}
