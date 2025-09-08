import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IStandardLibCall extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.StandardLibCall;
}
