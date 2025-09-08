import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IBreakStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.BreakStatement;
}
