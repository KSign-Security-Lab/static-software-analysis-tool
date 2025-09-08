import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IUserDefinedCall extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.UserDefinedCall;
}
