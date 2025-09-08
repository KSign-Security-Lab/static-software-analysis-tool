import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface ILiteral extends IBaseNode {
  nodeType: TemplateNodeTypes.Literal;
  size?: number;
  type: string;
  value: boolean | null | number | string;
}
