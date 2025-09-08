import { ICompoundStatement } from "./template/Block/CompoundStatement";
import { IBreakStatement } from "./template/ControlStructures/BreakStatement";
import { ICaseLabel } from "./template/ControlStructures/CaseLabel";
import { IContinueStatement } from "./template/ControlStructures/ContinueStatement";
import { IDefaultLabel } from "./template/ControlStructures/DefaultLabel";
import { IDoWhileStatement } from "./template/ControlStructures/DoWhileStatement";
import { IForStatement } from "./template/ControlStructures/ForStatement";
import { IGotoStatement } from "./template/ControlStructures/GotoStatement";
import { IIfStatement } from "./template/ControlStructures/IfStatement";
import { ILabel } from "./template/ControlStructures/Label";
import { IReturnStatement } from "./template/ControlStructures/ReturnStatement";
import { ISwitchStatement } from "./template/ControlStructures/SwitchStatement";
import { IWhileStatement } from "./template/ControlStructures/WhileStatement";
import { IEnumType } from "./template/DataTypes/EnumType";
import { IStructType } from "./template/DataTypes/StructType";
import { ITypeDefinition } from "./template/DataTypes/TypeDefinition";
import { IUnionType } from "./template/DataTypes/UnionType";
import { IAddressOfExpression } from "./template/Expressions/AddressOfExpression";
import { IArraySizeAllocation } from "./template/Expressions/ArraySizeAllocation";
import { IArraySubscriptExpression } from "./template/Expressions/ArraySubscriptExpression";
import { IAssignmentExpression } from "./template/Expressions/AssignmentExpression";
import { IBinaryExpression } from "./template/Expressions/BinaryExpression";
import { ICastExpression } from "./template/Expressions/CastExpression";
import { IIdentifier } from "./template/Expressions/Identifier";
import { ILiteral } from "./template/Expressions/Literal";
import { IMemberAccess } from "./template/Expressions/MemberAccess";
import { IPointerDereference } from "./template/Expressions/PointerDereference";
import { ISizeOfExpression } from "./template/Expressions/SizeOfExpression";
import { IStandardLibCall } from "./template/Expressions/StandardLibCall";
import { IUnaryExpression } from "./template/Expressions/UnaryExpression";
import { IUserDefinedCall } from "./template/Expressions/UserDefinedCall";
import { IIncludeDirective } from "./template/PreprocessorDirectives/IncludeDirective";
import { IMacroDefinition } from "./template/PreprocessorDirectives/MacroDefinition";
import { IArrayDeclaration } from "./template/ProgramStructures/ArrayDeclaration";
import { IFunctionDeclaration } from "./template/ProgramStructures/FunctionDeclaration";
import { IFunctionDefinition } from "./template/ProgramStructures/FunctionDefinition";
import { IParameterDeclaration } from "./template/ProgramStructures/ParameterDeclaration";
import { IParameterList } from "./template/ProgramStructures/ParameterList";
import { IPointerDeclaration } from "./template/ProgramStructures/PointerDeclaration";
import { ITranslationUnit } from "./template/ProgramStructures/TranslationUnit";
import { IVariableDeclaration } from "./template/ProgramStructures/VariableDeclaration";

export type TemplateNodes =
  | TemplateBlockNodes
  | TemplateControlStructureNodes
  | TemplateExpressionNodes
  | TemplatePreprocessorDirectiveNodes
  | TemplateProgramStructureNodes;

export type TemplateFlattenedNode = TemplateNodes & { id: number };

export interface TemplateFlattenedGraph {
  edges: { from: number; to: number }[];
  nodes: TemplateFlattenedNode[];
}

type TemplateBlockNodes = ICompoundStatement;

type TemplateControlStructureNodes =
  | IBreakStatement
  | ICaseLabel
  | IContinueStatement
  | IDefaultLabel
  | IDoWhileStatement
  | IEnumType
  | IForStatement
  | IGotoStatement
  | IIfStatement
  | ILabel
  | IReturnStatement
  | IStructType
  | ISwitchStatement
  | ITypeDefinition
  | IUnionType
  | IWhileStatement;

type TemplateExpressionNodes =
  | IAddressOfExpression
  | IArraySizeAllocation
  | IArraySubscriptExpression
  | IAssignmentExpression
  | IBinaryExpression
  | ICastExpression
  | IIdentifier
  | ILiteral
  | IMemberAccess
  | IPointerDereference
  | ISizeOfExpression
  | IStandardLibCall
  | IUnaryExpression
  | IUserDefinedCall;

type TemplatePreprocessorDirectiveNodes = IIncludeDirective | IMacroDefinition;

type TemplateProgramStructureNodes =
  | IArrayDeclaration
  | IFunctionDeclaration
  | IFunctionDefinition
  | IParameterDeclaration
  | IParameterList
  | IPointerDeclaration
  | ITranslationUnit
  | IVariableDeclaration;
