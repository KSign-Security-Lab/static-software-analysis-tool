import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IPointerDeclaration extends IBaseNode {
  level: number;
  name: string;
  nodeType: TemplateNodeTypes.PointerDeclaration;
  pointingType: string;
  storage?: string;
}
