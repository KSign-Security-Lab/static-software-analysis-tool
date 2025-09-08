import fs from "fs";
import path from "path";

import { validateCPGRoot } from "../cpg/validate/zod";
import { PlanationTool } from "../template/PlanationTool";
import { PostProcessor } from "../template/PostProcessor";
import { TemplateConverter } from "../template/TemplateConverter";
import { TemplateExtractor } from "../template/TemplateExtractor";
import { CPGRoot, TreeNode } from "../types/cpg";
import { TemplateFlattenedGraph, TemplateNodes } from "../types/node";
import { TemplateNodeTypes } from "../types/template/BaseNode/BaseNode";
import { writeJSONFiles } from "../utils/json";
import { TreeToText } from "../utils/treeToText";

// Usage: tsx script/generateTemplate.ts <input_json> <output_dir>
const args: string[] = process.argv.slice(2);

// ---- Strict CLI validation ----
if (args.length < 2) {
  console.error("Usage: tsx script/generateTemplate.ts <input_json> <output_dir>");
  process.exit(1);
}

const inputArg = path.resolve(args[0]);
const outDirArg = path.resolve(args[1]);

// 1) Ensure input is a SINGLE file with .json extension
let inputStat: fs.Stats;
try {
  inputStat = fs.statSync(inputArg);
} catch {
  console.error(`Input not found: ${inputArg}`);
  process.exit(1);
}
if (!inputStat.isFile()) {
  console.error(`Input must be a single JSON file, not a directory: ${inputArg}`);
  process.exit(1);
}
if (path.extname(inputArg).toLowerCase() !== ".json") {
  console.error(`Input must be a .json file: ${inputArg}`);
  process.exit(1);
}

// 2) Ensure output directory is PROVIDED and is a directory (create if needed)
try {
  if (fs.existsSync(outDirArg)) {
    const st = fs.statSync(outDirArg);
    if (!st.isDirectory()) {
      console.error(`Output path must be a directory, not a file: ${outDirArg}`);
      process.exit(1);
    }
  } else {
    fs.mkdirSync(outDirArg, { recursive: true });
  }
} catch (e) {
  console.error(`Failed to prepare output directory: ${outDirArg}\n${e instanceof Error ? e.message : String(e)}`);
  process.exit(1);
}

function verifyCPG(root: CPGRoot, inputFile: string): void {
  try {
    validateCPGRoot([root.export]);
    console.log(`Verified CPG GraphSON: ${path.basename(inputFile)}`);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Validation failed for ${path.basename(inputFile)}: ${msg}`);
  }
}

async function readCPG(inputFile: string): Promise<CPGRoot> {
  let root: CPGRoot;
  try {
    const raw = await fs.promises.readFile(inputFile, "utf8");
    root = JSON.parse(raw) as CPGRoot;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Read/parse error for ${path.basename(inputFile)}: ${msg}`);
  }
  return root;
}

function buildTemplateArtifacts(root: CPGRoot) {
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

  // Validate flatten ids uniqueness
  function collectIdsFromFlatten(graph: TemplateFlattenedGraph): number[] {
    const ids: number[] = [];
    for (const node of graph.nodes) {
      if (typeof node.id === "number") {
        ids.push(node.id);
      }
    }
    return ids;
  }
  const flattenIds = collectIdsFromFlatten(flatten[0]);
  const flattenUniqueIds = new Set(flattenIds);
  if (flattenIds.length !== flattenUniqueIds.size) {
    const duplicates = flattenIds.filter((id, idx) => flattenIds.indexOf(id) !== idx);
    throw new Error(`Duplicate node ids found in flattened template: ${[...new Set(duplicates)].join(", ")}`);
  }

  return { template, templateResult, textLines, flatten };
}

function saveOutputs(artifacts: ReturnType<typeof buildTemplateArtifacts>, inputFile: string, outDir: string): void {
  const parsed = path.parse(inputFile);
  const astOutPath = path.join(outDir, `${parsed.name}_astTree${parsed.ext}`);
  const templateOutPath = path.join(outDir, `${parsed.name}_templateTree${parsed.ext}`);
  const textFile = path.join(outDir, `${parsed.name}_text.txt`);
  const flattenOutPath = path.join(outDir, `${parsed.name}_flatten.json`);

  // writeSingleJSON(artifacts.template, astOutPath);
  writeSingleJSON(artifacts.templateResult, templateOutPath);
  // fs.writeFileSync(textFile, artifacts.textLines.join("\n\n"), "utf8");
  // writeSingleJSON(artifacts.flatten, flattenOutPath);

  console.log(
    `Generated: ${path.basename(astOutPath)}, ${path.basename(templateOutPath)}, ${path.basename(textFile)}, ${path.basename(flattenOutPath)}`
  );
}

async function main(inputFile: string, outDir: string): Promise<void> {
  const root = await readCPG(inputFile);
  verifyCPG(root, inputFile);
  const artifacts = buildTemplateArtifacts(root);
  saveOutputs(artifacts, inputFile, outDir);
}

function withContext<T>(fnName: string, fn: () => T): T {
  try {
    return fn();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`${fnName} failed: ${msg}`);
  }
}

function writeSingleJSON(item: TemplateFlattenedGraph[] | TemplateNodes[] | TreeNode[], outPath: string): string {
  const [written] = writeJSONFiles([item], [outPath]);
  return written;
}

void (async () => {
  await main(inputArg, outDirArg);
})().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
