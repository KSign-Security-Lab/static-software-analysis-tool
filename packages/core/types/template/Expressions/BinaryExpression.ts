import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IBinaryExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.BinaryExpression;
  operator: string;
  type: string;
}
