import { IBaseNode, TemplateNodeTypes } from "./BaseNode/BaseTypes";

export interface IAddressOfExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.AddressOfExpression;
  type: string;
}

export interface IArraySizeAllocation extends IBaseNode {
  nodeType: TemplateNodeTypes.ArraySizeAllocation;
  length: number | string;
}

export interface IArraySubscriptExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.ArraySubscriptExpression;
}

export interface IAssignmentExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.AssignmentExpression;
  operator: string;
}

export interface IBinaryExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.BinaryExpression;
  operator: string;
  type: string;
}

export interface ICastExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.CastExpression;
  targetType: string;
}

export interface IIdentifier extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.Identifier;
  size?: string;
  type: string;
}

export interface ILiteral extends IBaseNode {
  nodeType: TemplateNodeTypes.Literal;
  type: string;
  size?: number;
  value: string;
}

export interface IMemberAccess extends IBaseNode {
  nodeType: TemplateNodeTypes.MemberAccess;
  type: string;
}

export interface IPointerDereference extends IBaseNode {
  nodeType: TemplateNodeTypes.PointerDereference;
}

export interface ISizeOfExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.SizeOfExpression;
}

export interface IStandardLibCall extends IBaseNode {
  name: string;
  nodeType: TemplateNodeTypes.StandardLibCall;
}

export interface IUnaryExpression extends IBaseNode {
  nodeType: TemplateNodeTypes.UnaryExpression;
  operator: string;
  type: string;
}

export interface IUserDefinedCall extends IBaseNode {
  nodeType: TemplateNodeTypes.UserDefinedCall;
}
