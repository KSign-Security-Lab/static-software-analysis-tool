import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IAssignmentExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.AssignmentExpression;
  operator: string;
}
