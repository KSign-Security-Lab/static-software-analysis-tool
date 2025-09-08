import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IVariableDeclaration extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.VariableDeclaration;
  storage?: string;
  type: string;
}
