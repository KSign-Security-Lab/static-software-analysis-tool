import { IBaseNode, TemplateNodeTypes } from "./BaseNode/BaseTypes";

export interface IEnumType extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.EnumType;
}

export interface IStructType extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.StructType;
}

export interface ITypeDefinition extends IBaseNode {
  nodeType: TemplateNodeTypes.TypeDefinition;
  name: string;
  underlyingType: string;
}

export interface IUnionType extends IBaseNode {
  nodeType: TemplateNodeTypes.UnionType;
  name: string;
}
