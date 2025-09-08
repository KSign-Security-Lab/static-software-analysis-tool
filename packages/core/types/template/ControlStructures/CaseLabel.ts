import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface ICaseLabel extends IBaseNode {
  nodeType: TemplateNodeTypes.CaseLabel;
}
