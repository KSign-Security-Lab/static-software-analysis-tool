import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IUnionType extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.UnionType;
}
