import { IBaseNode, TemplateNodeTypes } from "./BaseNode/BaseTypes";

export interface ICompoundStatement extends IBaseNode {
  nodeType: TemplateNodeTypes.CompoundStatement;
}
