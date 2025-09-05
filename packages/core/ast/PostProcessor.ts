import type { IIdentifier } from "@/types/ast/Expressions/Identifier";

import { ASTNodeTypes } from "@/types/ast/BaseNode/BaseNode";
import { CPGRoot, EdgeGeneric, FieldIdentifierVertexProperties, MemberVertexProperties, VertexGeneric } from "@/types/cpg";
import { ASTNodes } from "@/types/node";

export class PostProcessor {
  /**
   * Add code properties to all AST nodes and its children.
   * It uses the CPGRoot to fetch the code information.
   */
  public addCodeProperties(nodes: ASTNodes[], cpg: CPGRoot): ASTNodes[] {
    return nodes.map((node) => {
      const vertex = cpg.export["@value"].vertices.find((v) => v.id["@value"] === node.id);
      const code: string | undefined =
        vertex &&
        "CODE" in vertex.properties &&
        typeof vertex.properties.CODE === "object" &&
        typeof vertex.properties.CODE["@value"] === "object" &&
        Array.isArray(vertex.properties.CODE["@value"]["@value"])
          ? vertex.properties.CODE["@value"]["@value"].join("")
          : undefined;

      return {
        ...node,
        code,
        children: node.children ? this.addCodeProperties(node.children, cpg) : [],
      };
    });
  }

  /**
   * Isolate the TranslationUnit node from the AST.
   * It returns the first TranslationUnit node found in the AST.
   * If no TranslationUnit node is found, it throws an error.
   */
  public isolateTranslationUnit(nodes: ASTNodes[]): ASTNodes[] {
    const tu = nodes.filter((node) => node.nodeType === ASTNodeTypes.TranslationUnit);
    if (tu.length === 0) {
      throw new Error("No TranslationUnit node found in the provided AST");
    }
    return tu;
  }

  /**
   * Walk the AST and check current node's children has ArrayDeclaration and the next child of the ArrayDeclaration is ArraySizeAllocation.
   * If so, merge the ArraySizeAllocation into the ArrayDeclaration.
   * Merging process is to check if the ArrayDeclaration's length are equal to the length of the ArraySizeAllocation.
   * If they are equal, remove the ArraySizeAllocation and keep the ArrayDeclaration.
   * If they are not equal, keep the ArraySizeAllocation's length.
   */
  public mergeArraySizeAllocation(nodes: ASTNodes[]): ASTNodes[] {
    return nodes.map((node) => {
      if (!node.children) return node;

      const mergedChildren: ASTNodes[] = [];

      for (let i = 0; i < node.children.length; i++) {
        const current = node.children[i];
        const next = node.children[i + 1];

        if (current.nodeType === ASTNodeTypes.ArrayDeclaration && next.nodeType === ASTNodeTypes.ArraySizeAllocation) {
          const arrayDecl = current;
          const arraySize = next;

          mergedChildren.push({
            ...arrayDecl,
            length: arrayDecl.length === arraySize.length ? arrayDecl.length : arraySize.length,
            children: [...(arrayDecl.children ?? []), ...(arraySize.children ?? [])],
          });

          i++; // skip next (ArraySizeAllocation)
        } else {
          mergedChildren.push({
            ...current,
            children: current.children ? this.mergeArraySizeAllocation(current.children) : current.children,
          });
        }
      }

      return {
        ...node,
        children: mergedChildren,
      };
    });
  }

  /**
   * Walk the AST and remove any nodes with a missing or invalid nodeType,
   * inlining their children instead.
   */
  public removeInvalidNodes(nodes: ASTNodes[]): ASTNodes[] {
    return nodes.flatMap((node) => this.validateNode(node));
  }

  public updateMemberAccessTypeLength(nodes: ASTNodes[], cpg: CPGRoot): ASTNodes[] {
    const memberAccessNodes = this.findMemberAccessNodes(nodes);
    if (memberAccessNodes.length === 0) {
      return nodes; // No MemberAccess nodes to process
    }

    const memberAccessChildrenIdentifierNodes = memberAccessNodes
      .flatMap((node) => {
        if (!node.children) {
          return [];
        }
        // Narrow to identifiers so we can safely read 'type'
        return node.children.filter((child): child is IIdentifier => child.nodeType === ASTNodeTypes.Identifier);
      })
      .filter((child) => child.type === "<unknown>");
    const memberAccessChildrenIdentifierIds = memberAccessChildrenIdentifierNodes.map((child) => child.id);

    const fieldIdentifierNodes = cpg.export["@value"].vertices.filter((node) => memberAccessChildrenIdentifierIds.includes(node.id["@value"]));

    for (const node of fieldIdentifierNodes) {
      const nodeId = node.id["@value"];
      // Track the path of IDs and labels
      const pathSteps: string[] = [];
      this.pushPath(pathSteps, nodeId, cpg);

      const outgoingEdges = this.getOutgoingEdges(nodeId, cpg);
      const outgoingDominateEdges = outgoingEdges.filter((edge) => edge.label === "DOMINATE");
      if (outgoingDominateEdges.length !== 1) {
        throw new Error(
          `MemberAccess node ${nodeId.toString()} has ${outgoingDominateEdges.length.toString()} DOMINATE edges, expected 1.` +
            ` Path: ${pathSteps.join(" → ")}`
        );
      }
      const identifierId = outgoingDominateEdges[0].outV["@value"];
      this.pushPath(pathSteps, identifierId, cpg);

      const identifierIncomingEdges = this.getIncomingEdges(identifierId, cpg);
      const identifierIncomingEvalTypeEdges = identifierIncomingEdges.filter((edge) => edge.label === "EVAL_TYPE");
      if (identifierIncomingEvalTypeEdges.length !== 1) {
        throw new Error(
          `Identifier node ${identifierId.toString()} has ${identifierIncomingEvalTypeEdges.length.toString()} EVAL_TYPE edges, expected 1.` +
            ` Path: ${pathSteps.join(" → ")}`
        );
      }
      const typeId = identifierIncomingEvalTypeEdges[0].inV["@value"];
      this.pushPath(pathSteps, typeId, cpg);

      const typeIncomingEdges = this.getIncomingEdges(typeId, cpg);
      const typeIncomingRefEdges = typeIncomingEdges.filter((edge) => edge.label === "REF");
      if (typeIncomingRefEdges.length !== 1) {
        throw new Error(
          `Type node ${typeId.toString()} has ${typeIncomingRefEdges.length.toString()} REF edges, expected 1.` + ` Path: ${pathSteps.join(" → ")}`
        );
      }
      const typeDeclId = typeIncomingRefEdges[0].inV["@value"];
      this.pushPath(pathSteps, typeDeclId, cpg);

      const typeDeclNode = this.getNodeById(typeDeclId, cpg);
      if (!typeDeclNode) {
        throw new Error(`TypeDecl node ${typeDeclId.toString()} not found in CPG.` + ` Path: ${pathSteps.join(" → ")}`);
      }

      const typeDecleincomingEdges = this.getIncomingEdges(typeDeclId, cpg);
      const typeDeclIncomingAliasEdges = typeDecleincomingEdges.filter((edge) => edge.label === "ALIAS_OF");

      if (typeDeclIncomingAliasEdges.length > 1) {
        const aliasTypeId = typeDeclIncomingAliasEdges[0].inV["@value"];
        this.pushPath(pathSteps, aliasTypeId, cpg);

        const aliasTypeIncomingEdges = this.getIncomingEdges(aliasTypeId, cpg);
        const aliasTypeIncomingRefEdges = aliasTypeIncomingEdges.filter((edge) => edge.label === "REF");
        if (aliasTypeIncomingRefEdges.length !== 1) {
          throw new Error(
            `Alias type node ${aliasTypeId.toString()} has ${aliasTypeIncomingRefEdges.length.toString()} REF edges, expected 1.` +
              ` Path: ${pathSteps.join(" → ")}`
          );
        }
        const aliasTypeDeclId = aliasTypeIncomingRefEdges[0].inV["@value"];
        this.pushPath(pathSteps, aliasTypeDeclId, cpg);

        const matchingAliasMember = this.getMatchingMemberNodes(nodeId, aliasTypeDeclId, cpg);
        if (matchingAliasMember) {
          this.pushPath(pathSteps, matchingAliasMember.id["@value"], cpg);
          const memberProperties = matchingAliasMember.properties as MemberVertexProperties;
          const typeFullName = memberProperties.TYPE_FULL_NAME["@value"]["@value"].join("/");
          const size = typeFullName.includes("[") && typeFullName.includes("]") ? typeFullName.split("[")[1].split("]")[0] : "<unknown>";
          const type = typeFullName.includes("[") && typeFullName.includes("]") ? typeFullName.split("[")[0] : typeFullName;

          throw new Error(
            `Found matching member for MemberAccess node ${nodeId.toString()} in typeDecl ${typeDeclId.toString()}: ${memberProperties.NAME["@value"]["@value"].join("/")}, type: ${type}, size: ${size}`
          );
        } else {
          throw new Error(
            `No matching member found for MemberAccess node ${nodeId.toString()} in typeDecl ${typeDeclId.toString()} or alias typeDecl ${aliasTypeDeclId.toString()}.` +
              ` Path: ${pathSteps.join(" → ")}`
          );
        }
      } else {
        const matchingMember = this.getMatchingMemberNodes(nodeId, typeDeclId, cpg);
        if (matchingMember) {
          this.pushPath(pathSteps, matchingMember.id["@value"], cpg);
          const memberProperties = matchingMember.properties as MemberVertexProperties;
          const typeFullName = memberProperties.TYPE_FULL_NAME["@value"]["@value"].join("/");
          const size = typeFullName.includes("[") && typeFullName.includes("]") ? typeFullName.split("[")[1].split("]")[0] : "<unknown>";
          const type = typeFullName.includes("[") && typeFullName.includes("]") ? typeFullName.split("[")[0] : typeFullName;

          throw new Error(
            `Found matching member for MemberAccess node ${nodeId.toString()} in typeDecl ${typeDeclId.toString()}: ${memberProperties.NAME["@value"]["@value"].join("/")}, type: ${type}, size: ${size}`
          );
        }
      }
    }

    return nodes;
  }

  private findMemberAccessNodes(nodes: ASTNodes[]): ASTNodes[] {
    return nodes.flatMap((node) => {
      if (node.nodeType === ASTNodeTypes.MemberAccess) {
        return [node];
      }
      // If the node is not a MemberAccess, recurse into its children
      if (node.children) {
        return this.findMemberAccessNodes(node.children);
      }
      return [];
    });
  }

  private getIncomingEdges(nodeId: number, cpg: CPGRoot): EdgeGeneric[] {
    const edges = cpg.export["@value"].edges;
    const incomingKey = "outV";
    return edges.filter((edge) => edge[incomingKey]["@value"] === nodeId);
  }

  private getMatchingMemberNodes(memberAccessId: number, typeDeclId: number, cpg: CPGRoot): undefined | VertexGeneric {
    const typeDeclIncomingEdges = this.getIncomingEdges(typeDeclId, cpg);
    const typeDeclIncomingASTEdges = typeDeclIncomingEdges.filter((edge) => edge.label === "AST");
    if (typeDeclIncomingASTEdges.length === 0) {
      return undefined;
    }
    const membersId = typeDeclIncomingASTEdges.map((edge) => edge.inV["@value"]);
    const members = membersId.map((id) => this.getNodeById(id, cpg)).filter((node): node is VertexGeneric => node !== undefined);

    const memberAccessCpgNode = this.getNodeById(memberAccessId, cpg);
    if (!memberAccessCpgNode) {
      throw new Error(`MemberAccess node ${memberAccessId.toString()} not found in CPG.`);
    }
    const canonicalName = (memberAccessCpgNode.properties as FieldIdentifierVertexProperties).CANONICAL_NAME["@value"]["@value"].join("");
    const matchingMember = members.find(
      (member) => (member.properties as MemberVertexProperties).NAME["@value"]["@value"].join("") === canonicalName
    );
    return matchingMember;
  }

  private getNodeById(nodeId: number, cpg: CPGRoot): undefined | VertexGeneric {
    const nodes = cpg.export["@value"].vertices;
    return nodes.find((node) => node.id["@value"] === nodeId);
  }

  private getOutgoingEdges(nodeId: number, cpg: CPGRoot): EdgeGeneric[] {
    const edges = cpg.export["@value"].edges;
    const outgoingKey = "inV";
    return edges.filter((edge) => edge[outgoingKey]["@value"] === nodeId);
  }

  private pushPath(pathSteps: string[], nodeId: number, cpg: CPGRoot): void {
    const nodeType = this.getNodeById(nodeId, cpg)?.label ?? "UnknownNodeType";
    pathSteps.push(`${nodeType}(${nodeId.toString()})`);
  }

  private validateNode(node: ASTNodes): ASTNodes[] {
    const nodeKeys = Object.keys(node);
    if (!nodeKeys.includes("nodeType")) {
      // Inline grandchildren
      return (node.children ?? []).flatMap((child) => this.validateNode(child));
    }
    // Otherwise, keep this node but recurse into its children
    const processedChildren = (node.children ?? []).flatMap((child) => this.validateNode(child));
    return [
      {
        ...node,
        children: processedChildren,
      },
    ];
  }
}
