// No longer need fs imports since we're using PythonShell.runString
import path from "node:path";
import { fileURLToPath } from "node:url";
import { PythonShell } from "python-shell";

import { recursivelyGetFunctionsFromTemplate } from "../ast/utils";
import { validateIASTGraph } from "../ast/zod";
import { CPGGenerator } from "../cpg/CPGGenerator";
import { validateCPGRoot } from "../cpg/validate/zod";
import { DFGBuilder } from "../dfg/DFGBuilder";
import { PlanationTool } from "../template/PlanationTool";
import { PostProcessor } from "../template/PostProcessor";
import { TemplateConverter } from "../template/TemplateConverter";
import { TemplateExtractor } from "../template/TemplateExtractor";
import { IASTGraph } from "../types/ast";
import { CPGRoot, TreeNode } from "../types/cpg";
import { IDFGGraph } from "../types/dfg";
import { TemplateFlattenedGraph, TemplateNodes } from "../types/node";
import { TemplateNodeTypes } from "../types/template/BaseNode/BaseTypes";
import { getFilenameFromCPG } from "../utils";
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

export async function generateAst(template: TemplateNodes[]): Promise<IASTGraph> {
  if (!Array.isArray(template)) {
    throw new Error("generateAst expects an array of TemplateNodes");
  }

  // Resolve absolute path to ASTExtractor.py
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  const extractorPath = path.resolve(__dirname, "../ast/ASTExtractor.py");

  const functions = recursivelyGetFunctionsFromTemplate(template);
  const pythonExe = process.env.PYTHON_PATH ?? process.env.PYTHON ?? "python3";

  // Create Python code that loads the extractor and processes the data and returns IASTGraph
  const pyCode = [
    "import sys, json, importlib.util",
    `mod_path = r"${extractorPath}"`,
    "spec = importlib.util.spec_from_file_location('ast_extractor', mod_path)",
    "mod = importlib.util.module_from_spec(spec)",
    "spec.loader.exec_module(mod)",
    "Extractor = getattr(mod, 'ASTExtractorV1_12')",
    // Build ast_result list
    `roots = ${JSON.stringify(functions)}`,
    "ast_result = []",
    "for root in roots:",
    "    try:",
    "        ext = Extractor(root)",
    "        ast_result.append(ext.run())",
    "    except Exception as e:",
    "        ast_result.append({'error': str(e)})",
    // Create IASTGraph shape
    "graph = {'file': '', 'label': 0, 'ast_result': ast_result}",
    "print(json.dumps(graph, ensure_ascii=False))",
  ].join("\n");

  const options = {
    mode: "text" as const,
    pythonPath: pythonExe,
    pythonOptions: ["-u"], // unbuffered output
    timeout: 60000, // 60 seconds timeout
  };

  return PythonShell.runString(pyCode, options)
    .then((messages: string[]) => {
      const output = messages.join("");

      if (!output || output.trim() === "") {
        throw new Error("Python AST extraction failed: No output received");
      }

      try {
        const parsed: unknown = JSON.parse(output);
        const graph = validateIASTGraph(parsed);
        return graph;
      } catch (e) {
        const errorMessage = e instanceof Error ? e.message : String(e);
        throw new Error(
          `Invalid JSON from Python AST extractor: ${errorMessage}. Output length: ${String(output.length)}, Output preview: ${output.substring(0, 200)}...`
        );
      }
    })
    .catch((error: unknown) => {
      throw new Error(`Python AST extraction failed: ${error instanceof Error ? error.message : String(error)}`);
    });
}

export function generateDfg(cpg: CPGRoot, ast: IASTGraph): IDFGGraph[] {
  validateCPGRoot([cpg.export]);
  const templates = buildTemplateArtifacts(cpg);

  // Populate file from CPG if extractor didn't provide it
  if (!ast.file || ast.file.length === 0) {
    const inferred = getFilenameFromCPG(cpg);
    if (inferred) {
      (ast as { file: string }).file = inferred;
    }
  }

  const dfgBuilder = new DFGBuilder();
  const dfg = dfgBuilder.build(cpg, ast, templates.templateResult);
  return dfg;
}
