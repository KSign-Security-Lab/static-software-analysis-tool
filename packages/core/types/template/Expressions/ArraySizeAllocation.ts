import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IArraySizeAllocation extends IBaseNode {
  length: number | string;
  nodeType: TemplateNodeTypes.ArraySizeAllocation;
}
