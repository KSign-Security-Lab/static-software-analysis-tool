import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IEnumType extends IBaseNode {
  nodeType: TemplateNodeTypes.EnumType;
}
