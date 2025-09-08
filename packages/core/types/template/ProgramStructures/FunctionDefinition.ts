import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IFunctionDefinition extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.FunctionDefinition;
  returnType: string;
}
