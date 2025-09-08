import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IForStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.ForStatement;
}
