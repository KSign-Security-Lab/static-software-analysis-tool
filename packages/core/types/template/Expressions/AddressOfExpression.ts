import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface IAddressOfExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.AddressOfExpression;
  type: string;
}
