import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IStructType extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.StructType;
}
