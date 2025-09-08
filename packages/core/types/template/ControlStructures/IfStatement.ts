import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IIfStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.IfStatement;
}
