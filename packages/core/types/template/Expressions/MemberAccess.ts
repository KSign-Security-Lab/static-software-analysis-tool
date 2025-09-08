import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IMemberAccess extends IBaseNode {
  nodeType: TemplateNodeTypes.MemberAccess;
  type: string;
}
