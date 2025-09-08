import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface ICompoundStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.CompoundStatement;
}
