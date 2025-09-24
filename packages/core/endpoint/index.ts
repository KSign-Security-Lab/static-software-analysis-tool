// No longer need fs imports since we're using PythonShell.runString
import path from "node:path";
import { PythonShell } from "python-shell";

import { recursivelyGetFunctionsFromTemplate } from "../ast/utils";
import { validateIASTResults } from "../ast/zod";
import { CPGGenerator } from "../cpg/CPGGenerator";
import { validateCPGRoot } from "../cpg/validate/zod";
import { DFGBuilder } from "../dfg/DFGBuilder";
import { PlanationTool } from "../template/PlanationTool";
import { PostProcessor } from "../template/PostProcessor";
import { TemplateConverter } from "../template/TemplateConverter";
import { TemplateExtractor } from "../template/TemplateExtractor";
import { IASTResult } from "../types/ast";
import { CPGRoot, TreeNode } from "../types/cpg";
import { IDFGEdge, IDFGGraph, IDFGNode } from "../types/dfg";
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

export async function generateAst(template: TemplateNodes[]): Promise<IASTResult[]> {
  if (!Array.isArray(template)) {
    throw new Error("generateAst expects an array of TemplateNodes");
  }

  // Resolve absolute path to ASTExtractor.py
  const extractorPath =
    process.env.NODE_ENV === "test"
      ? path.resolve(process.cwd(), "ast/ASTExtractor.py")
      : path.resolve(process.cwd(), "packages/core/ast/ASTExtractor.py");

  const functions = recursivelyGetFunctionsFromTemplate(template);
  const pythonExe = process.env.PYTHON_PATH ?? process.env.PYTHON ?? "python3";

  // Create Python code that loads the extractor and processes the data and returns IASTResult
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
    "print(json.dumps(ast_result, ensure_ascii=False))",
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
        const graph = validateIASTResults(parsed);
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

export function generateDfg(cpg: CPGRoot, ast: IASTResult[]): IDFGGraph[] {
  validateCPGRoot([cpg.export]);
  const templates = buildTemplateArtifacts(cpg);

  const dfgBuilder = new DFGBuilder();
  const dfg = dfgBuilder.build(cpg, ast, templates.templateResult);
  return dfg;
}

export const DFG_EXTRACTOR_PATH = path.join(__dirname, "../DFGExtractor.py");

export async function runPythonDFGExtractor(templateData: TemplateNodes[]): Promise<IDFGGraph[]> {
  const dfgGraphs: IDFGGraph[] = [];
  const templateFunctions = recursivelyGetFunctionsFromTemplate(templateData);
  const astData = await generateAst(templateData);

  if (astData.length !== templateFunctions.length) {
    throw new Error("AST data and template functions length mismatch");
  }

  for (let i = 0; i < templateFunctions.length; i++) {
    const templateFunction = templateFunctions[i];
    const astFunction = astData[i];
    const pythonCode = [
      "import sys",
      "import json",
      "import importlib.util",
      "import os",
      "from datetime import datetime",
      "",
      "# Load DFG extractor",
      `dfg_extractor_path = r"${DFG_EXTRACTOR_PATH}"`,
      "dfg_spec = importlib.util.spec_from_file_location('dfg_extractor', dfg_extractor_path)",
      "dfg_mod = importlib.util.module_from_spec(dfg_spec)",
      "dfg_spec.loader.exec_module(dfg_mod)",
      "",
      "# Get DFG extractor class",
      "DFGExtractor = getattr(dfg_mod, 'DFGExtractorV1_12')",
      "",
      "try:",
      "    # Parse input data",
      `    template_data = ${JSON.stringify(templateFunction).replace(/false/g, "False").replace(/true/g, "True").replace(/null/g, "None")}`,
      `    ast_result = ${JSON.stringify(astFunction).replace(/false/g, "False").replace(/true/g, "True").replace(/null/g, "None")}`,
      "",
      "    # Redirect stdout to stderr to capture debug messages",
      "    import sys",
      "    from contextlib import redirect_stdout",
      "    import io",
      "    ",
      "    # Capture stdout to filter out debug messages",
      "    captured_output = io.StringIO()",
      "    ",
      "    with redirect_stdout(captured_output):",
      "        # Extract DFG using CPG data and AST result from endpoint",
      "        dfg_extractor = DFGExtractor(template_data, ast_result)",
      "        result = dfg_extractor.run()",
      "    ",
      "    # Print only JSON to stdout for the test",
      "    print(json.dumps(result, ensure_ascii=False))",
      "    ",
      "except Exception as e:",
      '    error_msg = f"Python DFG extraction failed: {str(e)}"',
      '    print(f"ERROR: {error_msg}", file=sys.stderr)',
      "    sys.exit(1)",
    ].join("\n");

    const options = {
      mode: "text" as const,
      pythonPath: process.env.PYTHON_PATH ?? process.env.PYTHON ?? "python3",
      pythonOptions: ["-u"],
      timeout: 60000,
    };

    const graphs = await new Promise<IDFGGraph[]>((resolve, reject) => {
      PythonShell.runString(pythonCode, options)
        .then((messages) => {
          const output = messages.join("");
          const errorOutput = messages.filter((msg: string) => msg.trim().startsWith("ERROR:")).join("\n");

          if (errorOutput) {
            const actualErrors = errorOutput
              .split("\n")
              .map((s) => s.trim())
              .filter((line) => line.startsWith("ERROR:") && !line.includes("node_type not in CONTROL_NODES"))
              .join("\n");

            if (actualErrors.trim()) {
              reject(new Error(actualErrors.replace("ERROR: ", "")));
              return;
            }
          }

          if (!output || output.trim() === "") {
            reject(new Error("Python DFG extraction failed: No output received"));
            return;
          }

          try {
            const parsed = JSON.parse(output) as unknown;
            if (parsed && typeof parsed === "object" && "nodes" in parsed && "edges_dfg" in parsed) {
              const pythonResult = parsed as { edges_dfg: unknown[]; nodes: unknown[] };
              const dfgGraph: IDFGGraph = {
                nodes: pythonResult.nodes as IDFGNode[],
                edges: pythonResult.edges_dfg as IDFGEdge[],
              };
              resolve([dfgGraph]);
            } else {
              resolve([parsed as IDFGGraph]);
            }
          } catch (e: unknown) {
            const errorMessage = e instanceof Error ? e.message : String(e);
            reject(new Error(`Invalid JSON from Python DFG extractor: ${errorMessage}. Output: ${output.substring(0, 200)}...`));
          }
        })
        .catch((error: unknown) => {
          reject(new Error(`Python DFG extraction failed: ${error instanceof Error ? error.message : String(error)}`));
        });
    });

    dfgGraphs.push(...graphs);
  }

  return dfgGraphs;
}
