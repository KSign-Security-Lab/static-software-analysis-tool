import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IFunctionDeclaration extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.FunctionDeclaration;
  returnType: string;
}
