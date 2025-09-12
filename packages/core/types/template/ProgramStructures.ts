import { IBaseNode, TemplateNodeTypes } from "./BaseNode/BaseTypes";

export interface IArrayDeclaration extends IBaseNode {
  elementType: string;
  length: number | string;
  name: string;
  nodeType: TemplateNodeTypes.ArrayDeclaration;
  storage?: string;
}

export interface IFunctionDeclaration extends IBaseNode {
  nodeType: TemplateNodeTypes.FunctionDeclaration;
}

export interface IFunctionDefinition extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.FunctionDefinition;
  returnType: string;
}

export interface IParameterDeclaration extends IBaseNode {
  nodeType: TemplateNodeTypes.ParameterDeclaration;
  name: string;
  type: string;
  size?: string;
}

export interface IParameterList extends IBaseNode {
  nodeType: TemplateNodeTypes.ParameterList;
}

export interface IPointerDeclaration extends IBaseNode {
  nodeType: TemplateNodeTypes.PointerDeclaration;
  name: string;
  pointingType: string;
  level: number;
}

export interface ITranslationUnit extends IBaseNode {
  nodeType: TemplateNodeTypes.TranslationUnit;
}

export interface IVariableDeclaration extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.VariableDeclaration;
  storage?: string;
  type: string;
}
