import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IUnaryExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.UnaryExpression;
  operator: string;
  type: string;
}
