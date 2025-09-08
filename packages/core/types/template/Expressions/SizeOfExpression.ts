import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface ISizeOfExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.SizeOfExpression;
}
