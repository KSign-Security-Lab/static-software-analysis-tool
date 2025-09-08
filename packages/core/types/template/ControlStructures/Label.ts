import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface ILabel extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.Label;
}
