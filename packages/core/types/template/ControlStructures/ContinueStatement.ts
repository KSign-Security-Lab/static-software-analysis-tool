import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IContinueStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.ContinueStatement;
}
