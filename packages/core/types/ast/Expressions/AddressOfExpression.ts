import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IAddressOfExpression extends IBaseNode {
  nodeType: ASTNodeTypes.AddressOfExpression;
  type: string;
}
