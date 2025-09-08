import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IPointerDereference extends IBaseNode {
  nodeType: TemplateNodeTypes.PointerDereference;
  type: string;
}
