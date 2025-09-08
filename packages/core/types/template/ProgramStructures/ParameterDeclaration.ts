import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IParameterDeclaration extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.ParameterDeclaration;
  size?: string;
  type: string;
}
