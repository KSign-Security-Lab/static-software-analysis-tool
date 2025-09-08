import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IWhileStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.WhileStatement;
}
