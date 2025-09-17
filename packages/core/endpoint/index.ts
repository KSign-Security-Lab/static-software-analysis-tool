import { CPGGenerator } from "../cpg/CPGGenerator";
import { validateCPGRoot } from "../cpg/validate/zod";
import { DFGBuilder } from "../dfg/DFGBuilder";
import { PlanationTool } from "../template/PlanationTool";
import { PostProcessor } from "../template/PostProcessor";
import { TemplateConverter } from "../template/TemplateConverter";
import { TemplateExtractor } from "../template/TemplateExtractor";
import { IASTResult } from "../types/ast";
import { CPGRoot, TreeNode } from "../types/cpg";
import { IDFGGraph } from "../types/dfg";
import { TemplateFlattenedGraph, TemplateNodes } from "../types/node";
import { TemplateNodeTypes } from "../types/template/BaseNode/BaseTypes";
import { TreeToText } from "../utils/treeToText";

function withContext<T>(fnName: string, fn: () => T): T {
  try {
    return fn();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`${fnName} failed: ${msg}`);
  }
}

function collectIdsFromFlatten(graph: TemplateFlattenedGraph): number[] {
  const ids: number[] = [];
  for (const node of graph.nodes) {
    if (typeof node.id === "number") {
      ids.push(node.id);
    }
  }
  return ids;
}

function buildTemplateArtifacts(root: CPGRoot): {
  flatten: TemplateFlattenedGraph[];
  template: TreeNode[];
  templateResult: TemplateNodes[];
  textLines: string[];
} {
  const extractor = new TemplateExtractor();
  const converter = new TemplateConverter();
  const postProcessor = new PostProcessor();
  const planationTool = new PlanationTool([
    TemplateNodeTypes.VariableDeclaration,
    TemplateNodeTypes.ArrayDeclaration,
    TemplateNodeTypes.PointerDeclaration,
    TemplateNodeTypes.ParameterDeclaration,
    TemplateNodeTypes.AssignmentExpression,
    TemplateNodeTypes.FunctionDeclaration,
    TemplateNodeTypes.FunctionDefinition,
    TemplateNodeTypes.StandardLibCall,
    TemplateNodeTypes.UserDefinedCall,
    TemplateNodeTypes.CastExpression,
    TemplateNodeTypes.MemberAccess,
    TemplateNodeTypes.PointerDereference,
    TemplateNodeTypes.AddressOfExpression,
    TemplateNodeTypes.ArraySubscriptExpression,
    TemplateNodeTypes.BinaryExpression,
    TemplateNodeTypes.UnaryExpression,
    TemplateNodeTypes.SizeOfExpression,
    TemplateNodeTypes.Identifier,
    TemplateNodeTypes.Literal,
  ]);
  const treeToText = new TreeToText(["properties", "line_no", "code"]);

  const template: TreeNode[] = withContext("getTemplateTree", () => extractor.getTemplateTree(root.export));
  const converted = withContext("convertTree", () => converter.convertTree(template));
  let templateResult: TemplateNodes[] = withContext("removeInvalidNodes", () => postProcessor.removeInvalidNodes(converted));
  templateResult = withContext("addCodeProperties", () => postProcessor.addCodeProperties(templateResult, root));

  const textLines = templateResult.map((rootNode) => treeToText.convert(rootNode));
  const flatten = planationTool.flatten(templateResult);

  const flattenIds = collectIdsFromFlatten(flatten[0]);
  const flattenUniqueIds = new Set(flattenIds);
  if (flattenIds.length !== flattenUniqueIds.size) {
    const duplicates = flattenIds.filter((id, idx) => flattenIds.indexOf(id) !== idx);
    throw new Error(`Duplicate node ids found in flattened template: ${[...new Set(duplicates)].join(", ")}`);
  }

  return { template, templateResult, textLines, flatten };
}

export async function generateCpg(filePath: string, type?: "file" | "string"): Promise<CPGRoot> {
  const cpgGenerator = new CPGGenerator();
  const cpgStandalone = await cpgGenerator.convertToCPGStandalone(filePath, type && type === "file" ? { filename: filePath } : undefined);
  validateCPGRoot([cpgStandalone.cpgData.export]);
  return cpgStandalone.cpgData;
}

export function generateTemplate(cpg: CPGRoot): TemplateNodes[] {
  validateCPGRoot([cpg.export]);
  const artifacts = buildTemplateArtifacts(cpg);
  return artifacts.templateResult;
}

export function generateAst(template: TemplateNodes[]): IASTResult[] {
  // In this simplified endpoint, assume template can be treated as AST-compatible data
  return template as unknown as IASTResult[];
}

export function generateDfg(cpg: CPGRoot, ast: IASTResult[]): IDFGGraph[] {
  validateCPGRoot([cpg.export]);
  const templates = buildTemplateArtifacts(cpg);
  const dfgBuilder = new DFGBuilder();
  const dfg = dfgBuilder.build(cpg, ast, templates.templateResult);
  return dfg;
}
