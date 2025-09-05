import { ICompoundStatement } from "./ast/Block/CompoundStatement";
import { IBreakStatement } from "./ast/ControlStructures/BreakStatement";
import { ICaseLabel } from "./ast/ControlStructures/CaseLabel";
import { IContinueStatement } from "./ast/ControlStructures/ContinueStatement";
import { IDefaultLabel } from "./ast/ControlStructures/DefaultLabel";
import { IDoWhileStatement } from "./ast/ControlStructures/DoWhileStatement";
import { IForStatement } from "./ast/ControlStructures/ForStatement";
import { IGotoStatement } from "./ast/ControlStructures/GotoStatement";
import { IIfStatement } from "./ast/ControlStructures/IfStatement";
import { ILabel } from "./ast/ControlStructures/Label";
import { IReturnStatement } from "./ast/ControlStructures/ReturnStatement";
import { ISwitchStatement } from "./ast/ControlStructures/SwitchStatement";
import { IWhileStatement } from "./ast/ControlStructures/WhileStatement";
import { IEnumType } from "./ast/DataTypes/EnumType";
import { IStructType } from "./ast/DataTypes/StructType";
import { ITypeDefinition } from "./ast/DataTypes/TypeDefinition";
import { IUnionType } from "./ast/DataTypes/UnionType";
import { IAddressOfExpression } from "./ast/Expressions/AddressOfExpression";
import { IArraySizeAllocation } from "./ast/Expressions/ArraySizeAllocation";
import { IArraySubscriptExpression } from "./ast/Expressions/ArraySubscriptExpression";
import { IAssignmentExpression } from "./ast/Expressions/AssignmentExpression";
import { IBinaryExpression } from "./ast/Expressions/BinaryExpression";
import { ICastExpression } from "./ast/Expressions/CastExpression";
import { IIdentifier } from "./ast/Expressions/Identifier";
import { ILiteral } from "./ast/Expressions/Literal";
import { IMemberAccess } from "./ast/Expressions/MemberAccess";
import { IPointerDereference } from "./ast/Expressions/PointerDereference";
import { ISizeOfExpression } from "./ast/Expressions/SizeOfExpression";
import { IStandardLibCall } from "./ast/Expressions/StandardLibCall";
import { IUnaryExpression } from "./ast/Expressions/UnaryExpression";
import { IUserDefinedCall } from "./ast/Expressions/UserDefinedCall";
import { IIncludeDirective } from "./ast/PreprocessorDirectives/IncludeDirective";
import { IMacroDefinition } from "./ast/PreprocessorDirectives/MacroDefinition";
import { IArrayDeclaration } from "./ast/ProgramStructures/ArrayDeclaration";
import { IFunctionDeclaration } from "./ast/ProgramStructures/FunctionDeclaration";
import { IFunctionDefinition } from "./ast/ProgramStructures/FunctionDefinition";
import { IParameterDeclaration } from "./ast/ProgramStructures/ParameterDeclaration";
import { IParameterList } from "./ast/ProgramStructures/ParameterList";
import { IPointerDeclaration } from "./ast/ProgramStructures/PointerDeclaration";
import { ITranslationUnit } from "./ast/ProgramStructures/TranslationUnit";
import { IVariableDeclaration } from "./ast/ProgramStructures/VariableDeclaration";

export type ASTNodes = ASTBlockNodes | ASTControlStructureNodes | ASTExpressionNodes | ASTPreprocessorDirectiveNodes | ASTProgramStructureNodes;

export type ASTFlattenedNode = ASTNodes & { id: number };

export interface ASTFlattenedGraph {
  edges: { from: number; to: number }[];
  nodes: ASTFlattenedNode[];
}

type ASTBlockNodes = ICompoundStatement;

type ASTControlStructureNodes =
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

type ASTExpressionNodes =
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

type ASTPreprocessorDirectiveNodes = IIncludeDirective | IMacroDefinition;

type ASTProgramStructureNodes =
  | IArrayDeclaration
  | IFunctionDeclaration
  | IFunctionDefinition
  | IParameterDeclaration
  | IParameterList
  | IPointerDeclaration
  | ITranslationUnit
  | IVariableDeclaration;
