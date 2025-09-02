import { ICompoundStatement } from "@/types/ast/Block/CompoundStatement";
import { IBreakStatement } from "@/types/ast/ControlStructures/BreakStatement";
import { ICaseLabel } from "@/types/ast/ControlStructures/CaseLabel";
import { IContinueStatement } from "@/types/ast/ControlStructures/ContinueStatement";
import { IDefaultLabel } from "@/types/ast/ControlStructures/DefaultLabel";
import { IDoWhileStatement } from "@/types/ast/ControlStructures/DoWhileStatement";
import { IForStatement } from "@/types/ast/ControlStructures/ForStatement";
import { IGotoStatement } from "@/types/ast/ControlStructures/GotoStatement";
import { IIfStatement } from "@/types/ast/ControlStructures/IfStatement";
import { ILabel } from "@/types/ast/ControlStructures/Label";
import { IReturnStatement } from "@/types/ast/ControlStructures/ReturnStatement";
import { ISwitchStatement } from "@/types/ast/ControlStructures/SwitchStatement";
import { IWhileStatement } from "@/types/ast/ControlStructures/WhileStatement";
import { IEnumType } from "@/types/ast/DataTypes/EnumType";
import { IStructType } from "@/types/ast/DataTypes/StructType";
import { ITypeDefinition } from "@/types/ast/DataTypes/TypeDefinition";
import { IUnionType } from "@/types/ast/DataTypes/UnionType";
import { IAddressOfExpression } from "@/types/ast/Expressions/AddressOfExpression";
import { IArraySizeAllocation } from "@/types/ast/Expressions/ArraySizeAllocation";
import { IArraySubscriptExpression } from "@/types/ast/Expressions/ArraySubscriptExpression";
import { IAssignmentExpression } from "@/types/ast/Expressions/AssignmentExpression";
import { IBinaryExpression } from "@/types/ast/Expressions/BinaryExpression";
import { ICastExpression } from "@/types/ast/Expressions/CastExpression";
import { IIdentifier } from "@/types/ast/Expressions/Identifier";
import { ILiteral } from "@/types/ast/Expressions/Literal";
import { IMemberAccess } from "@/types/ast/Expressions/MemberAccess";
import { IPointerDereference } from "@/types/ast/Expressions/PointerDereference";
import { ISizeOfExpression } from "@/types/ast/Expressions/SizeOfExpression";
import { IStandardLibCall } from "@/types/ast/Expressions/StandardLibCall";
import { IUnaryExpression } from "@/types/ast/Expressions/UnaryExpression";
import { IUserDefinedCall } from "@/types/ast/Expressions/UserDefinedCall";
import { IIncludeDirective } from "@/types/ast/PreprocessorDirectives/IncludeDirective";
import { IMacroDefinition } from "@/types/ast/PreprocessorDirectives/MacroDefinition";
import { IArrayDeclaration } from "@/types/ast/ProgramStructures/ArrayDeclaration";
import { IFunctionDeclaration } from "@/types/ast/ProgramStructures/FunctionDeclaration";
import { IFunctionDefinition } from "@/types/ast/ProgramStructures/FunctionDefinition";
import { IParameterDeclaration } from "@/types/ast/ProgramStructures/ParameterDeclaration";
import { IParameterList } from "@/types/ast/ProgramStructures/ParameterList";
import { IPointerDeclaration } from "@/types/ast/ProgramStructures/PointerDeclaration";
import { ITranslationUnit } from "@/types/ast/ProgramStructures/TranslationUnit";
import { IVariableDeclaration } from "@/types/ast/ProgramStructures/VariableDeclaration";

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
