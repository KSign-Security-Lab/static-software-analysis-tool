import { IBaseNode, TemplateNodeTypes } from "../BaseNode/BaseNode";

export interface ITypeDefinition extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.TypeDefinition;
  underlyingType: string;
}
