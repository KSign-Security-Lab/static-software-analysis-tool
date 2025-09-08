import { TemplateNodes } from "../../node";

export enum TemplateNodeTypes {
  AddressOfExpression = "AddressOfExpression",
  ArrayDeclaration = "ArrayDeclaration",
  ArraySizeAllocation = "ArraySizeAllocation",
  ArraySubscriptExpression = "ArraySubscriptExpression",
  AssignmentExpression = "AssignmentExpression",
  BinaryExpression = "BinaryExpression",
  BreakStatement = "BreakStatement",
  CaseLabel = "CaseLabel",
  CastExpression = "CastExpression",
  CompoundStatement = "CompoundStatement",
  ContinueStatement = "ContinueStatement",
  DefaultLabel = "DefaultLabel",
  DoWhileStatement = "DoWhileStatement",
  EnumType = "EnumType",
  ForStatement = "ForStatement",
  FunctionDeclaration = "FunctionDeclaration",
  FunctionDefinition = "FunctionDefinition",
  GotoStatement = "GotoStatement",
  Identifier = "Identifier",
  IfStatement = "IfStatement",
  IncludeDirective = "IncludeDirective",
  Label = "Label",
  Literal = "Literal",
  MacroDefinition = "MacroDefinition",
  MemberAccess = "MemberAccess",
  ParameterDeclaration = "ParameterDeclaration",
  ParameterList = "ParameterList",
  PointerDeclaration = "PointerDeclaration",
  PointerDereference = "PointerDereference",
  ReturnStatement = "ReturnStatement",
  SizeOfExpression = "SizeOfExpression",
  StandardLibCall = "StandardLibCall",
  StructType = "StructType",
  SwitchStatement = "SwitchStatement",
  TranslationUnit = "TranslationUnit",
  TypeDefinition = "TypeDefinition",
  UnaryExpression = "UnaryExpression",
  UnionType = "UnionType",
  UserDefinedCall = "UserDefinedCall",
  VariableDeclaration = "VariableDeclaration",
  WhileStatement = "WhileStatement",
}

export interface IBaseNode {
  children?: TemplateNodes[];
  code?: string;
  id: number;
  nodeType: TemplateNodeTypes;
}
