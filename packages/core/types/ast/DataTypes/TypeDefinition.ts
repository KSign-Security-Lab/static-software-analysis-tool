import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface ITypeDefinition extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.TypeDefinition;
  underlyingType: string;
}
