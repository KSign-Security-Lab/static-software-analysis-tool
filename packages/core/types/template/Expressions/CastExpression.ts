import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface ICastExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.CastExpression;
  targetType: string;
}
