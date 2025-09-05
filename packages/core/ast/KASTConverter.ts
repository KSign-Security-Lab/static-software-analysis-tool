import { ASTNodeTypes } from "../types/ast/BaseNode/BaseNode";
import { ICompoundStatement } from "../types/ast/Block/CompoundStatement";
import { IBreakStatement } from "../types/ast/ControlStructures/BreakStatement";
import { ICaseLabel } from "../types/ast/ControlStructures/CaseLabel";
import { IDefaultLabel } from "../types/ast/ControlStructures/DefaultLabel";
import { IDoWhileStatement } from "../types/ast/ControlStructures/DoWhileStatement";
import { IForStatement } from "../types/ast/ControlStructures/ForStatement";
import { IGotoStatement } from "../types/ast/ControlStructures/GotoStatement";
import { IIfStatement } from "../types/ast/ControlStructures/IfStatement";
import { ILabel } from "../types/ast/ControlStructures/Label";
import { IReturnStatement } from "../types/ast/ControlStructures/ReturnStatement";
import { ISwitchStatement } from "../types/ast/ControlStructures/SwitchStatement";
import { IWhileStatement } from "../types/ast/ControlStructures/WhileStatement";
import { IStructType } from "../types/ast/DataTypes/StructType";
import { ITypeDefinition } from "../types/ast/DataTypes/TypeDefinition";
import { IUnionType } from "../types/ast/DataTypes/UnionType";
import { IAddressOfExpression } from "../types/ast/Expressions/AddressOfExpression";
import { IArraySizeAllocation } from "../types/ast/Expressions/ArraySizeAllocation";
import { IArraySubscriptExpression } from "../types/ast/Expressions/ArraySubscriptExpression";
import { IAssignmentExpression } from "../types/ast/Expressions/AssignmentExpression";
import { IBinaryExpression } from "../types/ast/Expressions/BinaryExpression";
import { ICastExpression } from "../types/ast/Expressions/CastExpression";
import { IIdentifier } from "../types/ast/Expressions/Identifier";
import { ILiteral } from "../types/ast/Expressions/Literal";
import { IMemberAccess } from "../types/ast/Expressions/MemberAccess";
import { IPointerDereference } from "../types/ast/Expressions/PointerDereference";
import { ISizeOfExpression } from "../types/ast/Expressions/SizeOfExpression";
import { IStandardLibCall } from "../types/ast/Expressions/StandardLibCall";
import { IUnaryExpression } from "../types/ast/Expressions/UnaryExpression";
import { IUserDefinedCall } from "../types/ast/Expressions/UserDefinedCall";
import { IIncludeDirective } from "../types/ast/PreprocessorDirectives/IncludeDirective";
import { IArrayDeclaration } from "../types/ast/ProgramStructures/ArrayDeclaration";
import { IFunctionDeclaration } from "../types/ast/ProgramStructures/FunctionDeclaration";
import { IFunctionDefinition } from "../types/ast/ProgramStructures/FunctionDefinition";
import { IParameterDeclaration } from "../types/ast/ProgramStructures/ParameterDeclaration";
import { IParameterList } from "../types/ast/ProgramStructures/ParameterList";
import { IPointerDeclaration } from "../types/ast/ProgramStructures/PointerDeclaration";
import { ITranslationUnit } from "../types/ast/ProgramStructures/TranslationUnit";
import { IVariableDeclaration } from "../types/ast/ProgramStructures/VariableDeclaration";
import {
  CallVertexProperties,
  ControlStructureVertexProperties,
  IdentifierVertexProperties,
  ImportVertexProperties,
  JumpTargetVertexProperties,
  LiteralVertexProperties,
  LocalVertexProperties,
  MethodParameterInVertexProperties,
  MethodRefVertexProperties,
  MethodVertexProperties,
  TreeNode,
  TypeDeclVertexProperties,
} from "../types/cpg";
import { ASTNodes } from "../types/node";
import { randomIntWithLength } from "../utils";
import { BinaryUnaryTypeWrapper } from "./BinaryUnaryTypeWrapper";
import { BinaryExpressionOperatorMap } from "./config/BinaryExpression";
import {
  IdentifierToLiteralMap,
  PredefinedIdentifierTypes,
} from "./config/Predefined";
import { STANDARD_LIB_CALLS } from "./config/StandardLibCall";
import { UnaryExpressionOperatorMap } from "./config/UnaryExpression";

type CallOperatorsReturnTypes =
  | IAddressOfExpression
  | IArraySizeAllocation
  | IArraySubscriptExpression
  | IAssignmentExpression
  | IBinaryExpression
  | ICastExpression
  | ILiteral
  | IMemberAccess
  | ISizeOfExpression
  | IUnaryExpression
  | undefined;

type CallReturnTypes =
  | CallOperatorsReturnTypes
  | IStandardLibCall
  | IUserDefinedCall;

export class KASTConverter {
  private callCollection: string[];

  constructor() {
    this.callCollection = [];
  }

  /** Convert an array (“forest”) of root nodes into ASTNodes[], skipping undefined conversions. */
  public convertTree(nodes: TreeNode[]): ASTNodes[] {
    const convertedNodes: ASTNodes[] = [];
    for (const node of nodes) {
      const single = this.dispatchConvert(node);
      if (single !== undefined) {
        convertedNodes.push(single);
      }
    }

    return convertedNodes;
  }

  public getCallCollection(): string[] {
    return this.callCollection;
  }

  private assertNever(x: unknown): never {
    throw new Error("Unexpected label: " + JSON.stringify(x));
  }

  private convertedChildren(children: TreeNode[]): ASTNodes[] {
    return children
      .map((child) => this.dispatchConvert(child))
      .filter((child): child is ASTNodes => child !== undefined);
  }

  /**
   * Dispatch helper: switch on node.label, extract payload, call the correct handler.
   * Returns ResultMap[...] or undefined.
   */
  private dispatchConvert(node: TreeNode): ASTNodes | undefined {
    try {
      switch (node.label) {
        case "BINDING":
        case "DEPENDENCY":
        case "META_DATA":
        case "METHOD_PARAMETER_OUT":
        case "METHOD_RETURN":
        case "MODIFIER":
        case "NAMESPACE":
        case "NAMESPACE_BLOCK":
        case "TYPE":
        case "TYPE_REF":
        case "UNKNOWN":
          return this.handleSkippedNodes(node);

        case "BLOCK":
          return this.handleBlock(node);
        case "CALL":
          return this.handleCall(node);
        case "CONTROL_STRUCTURE":
          return this.handleControlStructure(node);
        case "FIELD_IDENTIFIER":
          return this.handleFieldIdentifier(node);
        case "FILE":
          return this.handleFile(node);
        case "IDENTIFIER":
          return this.handleIdentifier(node);
        case "IMPORT":
          return this.handleImport(node);
        case "JUMP_TARGET":
          return this.handleJumpTarget(node);
        case "LITERAL":
          return this.handleLiteral(node);
        case "LOCAL":
          return this.handleLocal(node);
        case "MEMBER":
          return this.handleMember(node);
        case "METHOD":
          return this.handleMethod(node);
        case "METHOD_PARAMETER_IN":
          return this.handleMethodParamIn(node);
        case "METHOD_REF":
          return this.handleMethodRef(node);
        case "RETURN":
          return this.handleReturn(node);
        case "TYPE_DECL":
          return this.handleTypeDecl(node);
        default:
          return this.assertNever(node.label);
      }
    } catch (error) {
      const lines: string[] = [
        `Error converting node:`,
        `  • id:      ${node.id}`,
        `  • label:   ${node.label}`,
        `  • name:    ${node.name}`,
        ``,
        `Original error message:`,
        `  ${error instanceof Error ? error.message : String(error)}`,
        ``,
        `Stack trace:`,
        error instanceof Error && error.stack ? error.stack : "n/a",
      ];
      console.error(lines.join("\n"));
      throw new Error(
        `Conversion failed for node id=${node.id} label=${node.label} name=${node.name}: ${error instanceof Error ? error.message : String(error)}`,
      );
    }
  }

  private formatString(str: string): string {
    // Format the string to remove quotes and escape characters.
    return str.replace(/"/g, "").replace(/\\n/g, "\n").replace(/\\t/g, "\t");
  }

  private handleBlock(node: TreeNode): ICompoundStatement | undefined {
    return {
      nodeType: ASTNodeTypes.CompoundStatement,
      id: Number(node.id) || -999,
      children: this.convertedChildren(node.children),
    };
  }

  private handleCall(node: TreeNode): CallReturnTypes {
    if (!this.callCollection.includes(node.name)) {
      this.callCollection.push(node.name);
    }

    if (node.name.startsWith("<operator>.")) {
      return this.handleCallOperators(node);
    }

    const paramListWrapper: IParameterList = {
      nodeType: ASTNodeTypes.ParameterList,
      id: randomIntWithLength(node.id.length) || -999,
      children: this.convertedChildren(node.children),
    };

    return {
      nodeType: STANDARD_LIB_CALLS.has(node.name)
        ? ASTNodeTypes.StandardLibCall
        : ASTNodeTypes.UserDefinedCall,
      id: Number(node.id) || -999,
      name: node.name,
      children: [paramListWrapper],
    };
  }

  private handleCallOperators(node: TreeNode): CallOperatorsReturnTypes {
    const properties = node.properties as unknown as CallVertexProperties;

    if (Object.keys(BinaryExpressionOperatorMap).includes(node.name)) {
      return {
        nodeType: ASTNodeTypes.BinaryExpression,
        id: Number(node.id) || -999,
        operator: BinaryExpressionOperatorMap[node.name],
        type: BinaryUnaryTypeWrapper(node),
        children: this.convertedChildren(node.children),
      };
    }

    if (Object.keys(UnaryExpressionOperatorMap).includes(node.name)) {
      return {
        nodeType: ASTNodeTypes.UnaryExpression,
        id: Number(node.id) || -999,
        operator: UnaryExpressionOperatorMap[node.name],
        type: BinaryUnaryTypeWrapper(node),
        children: this.convertedChildren(node.children),
      };
    }

    switch (node.name) {
      case "<operator>.addressOf": {
        const identifierChild = node.children
          .filter((child) => child.label === "IDENTIFIER")
          .find((child) => child.name === node.code.replace("&", ""));

        return {
          nodeType: ASTNodeTypes.AddressOfExpression,
          id: Number(node.id) || -999,
          type: identifierChild
            ? (
                identifierChild.properties as unknown as IdentifierVertexProperties
              ).TYPE_FULL_NAME["@value"]["@value"].join("/") + "*"
            : "<unknown>",
          children: this.convertedChildren(node.children),
        };
      }
      case "<operator>.assignment": {
        if (node.children.length !== 2) {
          throw new Error(
            `Call node ${node.id} has ${node.children.length.toString()} children, expected 2.`,
          );
        }
        const allocChild = node.children.filter(
          (child) => child.name === "<operator>.alloc",
        );

        if (allocChild.length === 1) {
          const typeFullName =
            properties.TYPE_FULL_NAME["@value"]["@value"].join("/");

          // Safely extract the array size inside brackets, if present
          const rawSizeMatch = /\[(\d+)\]/.exec(typeFullName);
          const fullRawType = rawSizeMatch ? rawSizeMatch[1] : undefined;

          // Determine length: numeric if possible, otherwise fallback to the full type name
          const length: number | string =
            fullRawType !== undefined
              ? Number(fullRawType) || fullRawType
              : typeFullName;

          return {
            nodeType: ASTNodeTypes.ArraySizeAllocation,
            id: Number(node.id) || -999,
            length,
            children: this.convertedChildren(node.children),
          };
        }

        return {
          nodeType: ASTNodeTypes.AssignmentExpression,
          id: Number(node.id) || -999,
          operator: "=",
          children: this.convertedChildren(node.children),
        };
      }
      case "<operator>.cast": {
        const filteredCastingType = node.code.split(")")[0].split("(")[1]; // eg. "(char *)ALLOCA((10)*sizeof(char))"w
        return {
          nodeType: ASTNodeTypes.CastExpression,
          id: Number(node.id) || -999,
          targetType: filteredCastingType || node.code, // TODO:  This should be the type of the cast, not the code.
          children: this.convertedChildren(
            node.children.filter((child) => child.label !== "TYPE_REF"),
          ), // TODO: Force removal of TYPE_REF children, as they are not needed in the cast expression.
        };
      }
      case "<operator>.fieldAccess":
      case "<operator>.indirectFieldAccess": {
        return {
          nodeType: ASTNodeTypes.MemberAccess,
          id: Number(node.id) || -999,
          type: properties.TYPE_FULL_NAME["@value"]["@value"].join("/"),
          children: this.convertedChildren(node.children),
        };
      }
      case "<operator>.indirectIndexAccess": {
        return {
          nodeType: ASTNodeTypes.ArraySubscriptExpression,
          id: Number(node.id) || -999,
          children: this.convertedChildren(node.children),
        };
      }
      case "<operator>.sizeOf": {
        return {
          nodeType: ASTNodeTypes.SizeOfExpression,
          id: Number(node.id) || -999,
          children: this.convertedChildren(node.children),
        };
      }
    }

    // TODO: Change to undefined after development, temopral fix to handle childen that does not match the label yet.
    return {
      ...node,
      children: node.children
        .map((child) => this.dispatchConvert(child))
        .filter((child): child is ASTNodes => child !== undefined),
    } as unknown as IAssignmentExpression;
  }

  private handleControlStructure(
    node: TreeNode,
  ):
    | IBreakStatement
    | IDoWhileStatement
    | IForStatement
    | IGotoStatement
    | IIfStatement
    | ISwitchStatement
    | IWhileStatement
    | undefined {
    const properties =
      node.properties as unknown as ControlStructureVertexProperties;

    const controlStructureType =
      properties.CONTROL_STRUCTURE_TYPE["@value"]["@value"][0];

    switch (controlStructureType) {
      case "BREAK": {
        return {
          nodeType: ASTNodeTypes.BreakStatement,
          id: Number(node.id) || -999,
          children: this.convertedChildren(node.children),
        };
      }
      case "DO": {
        return {
          nodeType: ASTNodeTypes.DoWhileStatement,
          id: Number(node.id) || -999,
          children: this.convertedChildren(node.children),
        };
      }
      case "FOR": {
        return {
          nodeType: ASTNodeTypes.ForStatement,
          id: Number(node.id) || -999,
          children: this.convertedChildren(node.children),
        };
      }
      case "GOTO": {
        return {
          nodeType: ASTNodeTypes.GotoStatement,
          id: Number(node.id) || -999,
          jumpTarget: node.code.split("goto ")[1].replace(";", "") || node.code, // Extract the jump target from the code.
          children: this.convertedChildren(node.children),
        };
      }
      case "IF": {
        if (node.children.length < 2) {
          throw new Error(
            `Control structure node ${node.id} has ${node.children.length.toString()} children, expected at least 2.`,
          );
        }

        const conditionChild = this.dispatchConvert(node.children[0]);
        const ifTrueChild = this.dispatchConvert(node.children[1]);
        // Unpack the children of the else branch
        // else node starts with "else" control structure, we do not need the wrapping control structure node.
        const elseBranch = node.children[2]
          ? this.dispatchConvert(node.children[2])
          : undefined;
        const elseChild =
          elseBranch && Array.isArray(elseBranch.children)
            ? elseBranch.children[0]
            : undefined;

        const restructuredChildren = [];

        if (conditionChild) restructuredChildren.push(conditionChild);
        if (ifTrueChild) restructuredChildren.push(ifTrueChild);
        if (elseChild) restructuredChildren.push(elseChild);

        return {
          nodeType: ASTNodeTypes.IfStatement,
          id: Number(node.id) || -999,
          children: restructuredChildren,
        };
      }
      case "SWITCH": {
        const blockChild = this.reshapeLabelChildren(
          node.children.find((child) => child.label === "BLOCK")?.children ??
            [],
        );
        const fullChildren = node.children
          .filter((child) => child.label !== "BLOCK")
          .concat(blockChild);

        return {
          nodeType: ASTNodeTypes.SwitchStatement,
          id: Number(node.id) || -999,
          children: this.convertedChildren(fullChildren),
        };
      }
      case "WHILE": {
        return {
          nodeType: ASTNodeTypes.WhileStatement,
          id: Number(node.id) || -999,
          children: this.convertedChildren(node.children),
        };
      }
    }

    // TODO: Change to undefined after development, temoporal fix to handle childen that does not match the label yet.
    return {
      ...node,
      children: node.children
        .map((child) => this.dispatchConvert(child))
        .filter((child): child is ASTNodes => child !== undefined),
    } as unknown as IIfStatement;
  }

  private handleFieldIdentifier(node: TreeNode): IIdentifier | undefined {
    return {
      nodeType: ASTNodeTypes.Identifier,
      id: Number(node.id) || -999,
      name: node.name || node.code, // Use node.name if available, otherwise use node.code.
      size: "<unknown>", // TODO: For now, using "<unknown>" as size, this should be changed to a proper size property if available.
      type: "<unknown>", // TODO: For now, using "<unknown>" as type, this should be changed to a proper size property if available.
      children: this.convertedChildren(node.children),
    };
  }

  private handleFile(node: TreeNode): ITranslationUnit | undefined {
    if (node.name.endsWith(".c") || node.name.endsWith(".cpp")) {
      return {
        nodeType: ASTNodeTypes.TranslationUnit,
        id: Number(node.id) || -999,
        children: this.convertedChildren(node.children),
      };
    }

    return undefined;
  }

  private handleIdentifier(
    node: TreeNode,
  ): IIdentifier | ILiteral | IPointerDereference | undefined {
    const properties = node.properties as unknown as IdentifierVertexProperties;
    const typeFullName =
      properties.TYPE_FULL_NAME["@value"]["@value"].join("/") || "";
    const isArray = typeFullName.includes("[") && typeFullName.includes("]");
    const size = isArray
      ? typeFullName.split("[")[1].split("]")[0] || "<dynamic>"
      : "<not-array>";
    const type = isArray
      ? typeFullName.split("[")[0] // The type is the part before the first "[".
      : typeFullName; // If no type is found, use "<
    const predefinedType = Object.keys(PredefinedIdentifierTypes).includes(
      node.name,
    )
      ? PredefinedIdentifierTypes[
          node.name as keyof typeof PredefinedIdentifierTypes
        ]
      : undefined;

    if (type.includes("*")) {
      const pointerType = type.replace("*", "").trim();
      return {
        nodeType: ASTNodeTypes.PointerDereference,
        id: Number(node.id) || -999,
        type: pointerType,
        children: [
          {
            nodeType: ASTNodeTypes.Identifier,
            id: randomIntWithLength(node.id.length) || -999,
            name: node.name,
            type: predefinedType ?? type,
            size,
            children: this.convertedChildren(node.children),
          },
        ],
      };
    }

    if (IdentifierToLiteralMap.includes(node.name)) {
      return {
        nodeType: ASTNodeTypes.Literal,
        id: Number(node.id) || -999,
        type: predefinedType ?? type,
        value: node.name,
        children: this.convertedChildren(node.children),
      };
    }

    const baseObj: IIdentifier = {
      nodeType: ASTNodeTypes.Identifier,
      id: Number(node.id) || -999,
      name: node.name,
      type: predefinedType ?? type,
      children: this.convertedChildren(node.children),
    };

    if (isArray) {
      baseObj.size = size;
    }
    return baseObj;
  }

  private handleImport(node: TreeNode): IIncludeDirective | undefined {
    return undefined; // Drop imports for now, as they are not needed in the KAST.
    const properties = node.properties as unknown as ImportVertexProperties;
    return {
      nodeType: ASTNodeTypes.IncludeDirective,
      id: Number(node.id) || -999,
      name: properties.IMPORTED_AS["@value"]["@value"].join("/"),
      children: this.convertedChildren(node.children),
    };
  }

  private handleJumpTarget(
    node: TreeNode,
  ): ICaseLabel | IDefaultLabel | ILabel | undefined {
    const properties = node.properties as unknown as JumpTargetVertexProperties;
    if (node.name === "case") {
      return {
        nodeType: ASTNodeTypes.CaseLabel,
        id: Number(node.id) || -999,
        children: this.convertedChildren(node.children),
      };
    }
    if (node.name === "default") {
      return {
        nodeType: ASTNodeTypes.DefaultLabel,
        id: Number(node.id) || -999,
        children: this.convertedChildren(node.children),
      };
    }

    return {
      nodeType: ASTNodeTypes.Label,
      id: Number(node.id) || -999,
      name: properties.NAME["@value"]["@value"].join("/"),
      children: this.convertedChildren(node.children),
    };
  }

  private handleLiteral(node: TreeNode): ILiteral | undefined {
    const properties = node.properties as unknown as LiteralVertexProperties;
    if (node.children.length !== 0) {
      throw new Error(
        `Literal node ${node.id} has ${node.children.length.toString()} children, expected 0.`,
      );
    }
    const isString = properties.TYPE_FULL_NAME["@value"]["@value"]
      .join("/")
      .includes("char");
    const predefinedType = Object.keys(PredefinedIdentifierTypes).includes(
      node.name,
    )
      ? PredefinedIdentifierTypes[
          node.name as keyof typeof PredefinedIdentifierTypes
        ]
      : undefined;
    const baseObj: ILiteral = {
      nodeType: ASTNodeTypes.Literal,
      id: Number(node.id) || -999,
      type:
        predefinedType ??
        properties.TYPE_FULL_NAME["@value"]["@value"].join("/"),
      value: this.formatString(node.code),
    };

    if (isString) {
      baseObj.size = this.formatString(node.code).length;
    }

    return baseObj;
  }

  private handleLocal(
    node: TreeNode,
  ): IArrayDeclaration | IPointerDeclaration | IVariableDeclaration {
    const properties = node.properties as unknown as LocalVertexProperties;
    const predefinedType = Object.keys(PredefinedIdentifierTypes).includes(
      node.name,
    )
      ? PredefinedIdentifierTypes[
          node.name as keyof typeof PredefinedIdentifierTypes
        ]
      : undefined;
    const typeFullName =
      properties.TYPE_FULL_NAME["@value"]["@value"].join("/") || "";
    const storage =
      node.code.includes(typeFullName) &&
      node.code.trim().startsWith(typeFullName)
        ? undefined
        : node.code.split(typeFullName)[0].trim();

    if (properties.TYPE_FULL_NAME["@value"]["@value"].length > 0) {
      const typeFullName =
        properties.TYPE_FULL_NAME["@value"]["@value"].join("/");
      // ArrayDeclaration is a special case of VariableDeclaration
      // Checks type full name has [ and ], and if so, it is an array declaration.
      // Inside of [] is the size of the array and in front of [] is the type of the array.
      if (typeFullName.includes("[") && typeFullName.includes("]")) {
        const elementType = typeFullName.split("[")[0];
        const fullRawType = typeFullName.split("[")[1].split("]")[0];
        const length = Number(fullRawType) || fullRawType;

        return {
          nodeType: ASTNodeTypes.ArrayDeclaration,
          id: Number(node.id) || -999,
          name: node.name,
          elementType,
          length,
          storage,
          children: this.convertedChildren(node.children),
        };
      }

      // PointerDeclaration is a special case of VariableDeclaration
      // Checks type full name has *, and if so, it is an pointer declaration.
      // level depends on the number of * in the type full name.
      // points_to is the type of the pointer.
      if (typeFullName.includes("*")) {
        const level = typeFullName.split("*").length - 1;
        const pointsTo = typeFullName.replace("*", "");

        return {
          nodeType: ASTNodeTypes.PointerDeclaration,
          id: Number(node.id) || -999,
          name: node.name,
          pointingType: pointsTo,
          level,
          storage,
          children: this.convertedChildren(node.children),
        };
      }
    }

    return {
      nodeType: ASTNodeTypes.VariableDeclaration,
      id: Number(node.id) || -999,
      name: node.name,
      type:
        predefinedType ??
        properties.TYPE_FULL_NAME["@value"]["@value"].join("/"),
      storage,
      children: this.convertedChildren(node.children),
    };
  }

  private handleMember(
    node: TreeNode,
  ): IArrayDeclaration | IPointerDeclaration | IVariableDeclaration {
    return this.handleLocal(node); // Member is handled the same way as Local, so we can reuse the same method.
  }

  private handleMethod(
    node: TreeNode,
  ): IFunctionDeclaration | IFunctionDefinition | undefined {
    const properties = node.properties as unknown as MethodVertexProperties;

    const firstBlock = node.children.find((child) => child.label === "BLOCK");

    if (
      properties.FILENAME["@value"]["@value"][0] + ":<global>" ===
        properties.AST_PARENT_FULL_NAME["@value"]["@value"][0] &&
      !properties.IS_EXTERNAL["@value"]["@value"][0] &&
      properties.SIGNATURE["@value"]["@value"].join("/").length > 0
    ) {
      const paramList: IParameterList = {
        nodeType: ASTNodeTypes.ParameterList,
        id: randomIntWithLength(node.id.length) || -999,
        children: node.children
          .filter((child) => child.label === "METHOD_PARAMETER_IN")
          .map((child) => this.dispatchConvert(child))
          .filter(
            (child): child is IParameterDeclaration => child !== undefined,
          ),
      };
      if ((paramList.children ?? []).length === 0) {
        paramList.children = [
          {
            nodeType: ASTNodeTypes.ParameterDeclaration,
            id: randomIntWithLength(node.id.length) || -999,
            name: "<empty>",
            type: "<empty>",
            children: [],
          },
        ];
      }
      const nonFuncParamChildren = node.children
        .filter((child) => child.label !== "METHOD_PARAMETER_IN")
        .filter((child) => !["METHOD_RETURN", "MODIFIER"].includes(child.label)) // TODO: currently skipping METHOD_RETURN and MODIFIER children, as they are not needed in the function declaration.
        .filter(
          (child) => !(child.label === "BLOCK" && child.children.length === 0),
        )
        .map((child) => this.dispatchConvert(child))
        .filter((child): child is ASTNodes => child !== undefined);

      return {
        nodeType:
          firstBlock && firstBlock.code === "<empty>"
            ? ASTNodeTypes.FunctionDeclaration
            : ASTNodeTypes.FunctionDefinition,
        id: Number(node.id) || -999,
        name: node.name,
        returnType: properties.SIGNATURE["@value"]["@value"]
          .join("/")
          .split("(")[0],
        children: [paramList, ...nonFuncParamChildren],
      };
    }

    // TODO: Change to undefined after development, temoporal fix to handle childen that does not match the label yet.
    return {
      ...node,
      children: node.children
        .map((child) => this.dispatchConvert(child))
        .filter((child): child is ASTNodes => child !== undefined),
    } as unknown as IFunctionDeclaration;
  }

  private handleMethodParamIn(
    node: TreeNode,
  ): IParameterDeclaration | undefined {
    const properties =
      node.properties as unknown as MethodParameterInVertexProperties;
    if (properties.TYPE_FULL_NAME["@value"]["@value"].length === 0) {
      throw new Error(`Method parameter in node ${node.id} has no type.`);
    }
    const typeFullName =
      properties.TYPE_FULL_NAME["@value"]["@value"].join("/") || "";
    const isArray = typeFullName.includes("[") && typeFullName.includes("]");
    const size = isArray
      ? typeFullName.split("[")[1].split("]")[0] || "<dynamic>"
      : undefined;
    const type = isArray
      ? typeFullName.split("[")[0] // The type is the part before the first "[".
      : typeFullName; // If no type is found, use "<
    return {
      nodeType: ASTNodeTypes.ParameterDeclaration,
      id: Number(node.id) || -999,
      name: node.name,
      type: type,
      size,
      children: this.convertedChildren(node.children),
    };
  }

  private handleMethodRef(node: TreeNode): IIdentifier | undefined {
    const properties = node.properties as unknown as MethodRefVertexProperties;

    if (properties.TYPE_FULL_NAME["@value"]["@value"].length === 0) {
      throw new Error(`Method reference node ${node.id} has no type.`);
    }
    const name =
      properties.METHOD_FULL_NAME["@value"]["@value"].join("/") ||
      node.name ||
      "<unknown>";
    const typeFullName =
      properties.TYPE_FULL_NAME["@value"]["@value"].join("/") || "";
    const isArray = typeFullName.includes("[") && typeFullName.includes("]");
    const size = isArray
      ? typeFullName.split("[")[1].split("]")[0] || "<dynamic>"
      : undefined;
    const type = isArray
      ? typeFullName.split("[")[0] // The type is the part before the first "[".
      : typeFullName; // If no type is found, use "<unknown>".

    const predefinedType = Object.keys(PredefinedIdentifierTypes).includes(name)
      ? PredefinedIdentifierTypes[
          name as keyof typeof PredefinedIdentifierTypes
        ]
      : undefined;

    return {
      nodeType: ASTNodeTypes.Identifier,
      id: Number(node.id) || -999,
      name,
      type: predefinedType ?? type,
      size,
      children: this.convertedChildren(node.children),
    };
  }

  private handleReturn(node: TreeNode): IReturnStatement {
    return {
      nodeType: ASTNodeTypes.ReturnStatement,
      id: Number(node.id) || -999,
      children: this.convertedChildren(node.children),
    };
  }

  private handleSkippedNodes(node: TreeNode): ASTNodes | undefined {
    return {
      ...node,
      children: node.children
        .map((child) => this.dispatchConvert(child))
        .filter((child): child is ASTNodes => child !== undefined),
    } as unknown as ASTNodes;
  }

  private handleTypeDecl(
    node: TreeNode,
  ): IStructType | ITypeDefinition | IUnionType | undefined {
    const properties = node.properties as unknown as TypeDeclVertexProperties;

    if (node.code.includes("typedef struct")) {
      return {
        nodeType: ASTNodeTypes.StructType,
        id: Number(node.id) || -999,
        name: node.name,
        children: this.convertedChildren(
          node.children.filter(
            (child) => child.label !== "METHOD" && child.name !== "<clinit>",
          ),
        ), // TODO: Force removal of METHOD children, as they are not needed in the struct type.
      };
    }

    if (node.code.includes("typedef union")) {
      return {
        nodeType: ASTNodeTypes.UnionType,
        id: Number(node.id) || -999,
        name: node.name,
        children: this.convertedChildren(node.children),
      };
    }

    if (node.code.includes("typedef")) {
      return {
        nodeType: ASTNodeTypes.TypeDefinition,
        id: Number(node.id) || -999,
        name: node.name,
        underlyingType: properties.ALIAS_TYPE_FULL_NAME
          ? properties.ALIAS_TYPE_FULL_NAME["@value"]["@value"].join("/")
          : "<unknown>",
        children: this.convertedChildren(node.children),
      };
    }

    // TODO: Change to undefined after development, temoporal fix to handle childen that does not match the label yet.
    return {
      ...node,
      children: node.children
        .map((child) => this.dispatchConvert(child))
        .filter((child): child is ASTNodes => child !== undefined),
    } as unknown as IStructType;
  }

  /**
   * Reshape the children of a switch label node to match the expected structure.
   * Loops through the children from jump target to the next jump target
   * and append to the jump target's children.
   */
  private reshapeLabelChildren(children: TreeNode[]): TreeNode[] {
    const reshapedChildren: TreeNode[] = [];
    let currentLabel: null | TreeNode = null;

    for (const child of children) {
      if (
        child.label === "JUMP_TARGET" &&
        (child.name === "case" || child.name === "default")
      ) {
        if (currentLabel) {
          reshapedChildren.push(currentLabel);
        }
        currentLabel = child; // Start a new label.
      } else if (currentLabel) {
        currentLabel.children.push(child);
      } else {
        reshapedChildren.push(child);
      }
    }

    if (currentLabel) {
      reshapedChildren.push(currentLabel); // Add the last label if it exists.
    }

    return reshapedChildren;
  }
}
