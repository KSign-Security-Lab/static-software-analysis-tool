import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IArrayDeclaration extends IBaseNode {
  elementType: string;
  length: number | string;
  name: string;
  nodeType: TemplateNodeTypes.ArrayDeclaration;
  storage?: string;
}
