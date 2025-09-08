import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IReturnStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.ReturnStatement;
}
