import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IIdentifier extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.Identifier;
  size?: string;
  type: string;
}
