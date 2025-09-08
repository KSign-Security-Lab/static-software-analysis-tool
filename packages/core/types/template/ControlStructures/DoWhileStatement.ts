import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IDoWhileStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.DoWhileStatement;
}
