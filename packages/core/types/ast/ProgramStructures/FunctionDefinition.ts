import { ASTNodeTypes, IBaseNode } from "../BaseNode/BaseNode";

export interface IFunctionDefinition extends IBaseNode {
  name: string;
  nodeType: ASTNodeTypes.FunctionDefinition;
  returnType: string;
}
