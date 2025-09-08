import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IArraySubscriptExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.ArraySubscriptExpression;
}
