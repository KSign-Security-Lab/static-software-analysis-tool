import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IFunctionDeclaration extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.FunctionDeclaration;
  returnType: string;
}
