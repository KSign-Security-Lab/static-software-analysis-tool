import fs from "fs";
import path from "path";

import { ASTExtractor } from "@/ast/ASTExtractor";
import { KASTConverter } from "@/ast/KASTConverter";
import { PlanationTool } from "@/ast/PlanationTool";
import { PostProcessor } from "@/ast/PostProcessor";
import { validateCPGRoot } from "@/cpg/validate/zod";
import { ASTNodeTypes } from "@/types/ast/BaseNode/BaseNode";
import { CPGRoot, TreeNode } from "@/types/cpg";
import { ASTGraph, ASTNodes } from "@/types/node";
import { writeJSONFiles } from "@/utils/json";
import { TreeToText } from "@/utils/treeToText";

// Usage: tsx src/script/generateAST.ts <input_json> <output_dir>
const args: string[] = process.argv.slice(2);

// ---- Strict CLI validation ----
if (args.length < 2) {
  console.error("Usage: tsx src/script/generateAST.ts <input_json> <output_dir>");
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

async function main(inputFile: string, outDir: string): Promise<void> {
  // Read and parse single CPG JSON
  let root: CPGRoot;
  try {
    const raw = await fs.promises.readFile(inputFile, "utf8");
    root = JSON.parse(raw) as CPGRoot;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Read/parse error for ${path.basename(inputFile)}: ${msg}`);
  }

  // Verify GraphSON structure
  try {
    validateCPGRoot([root.export]);
    console.log(`Verified CPG GraphSON: ${path.basename(inputFile)}`);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Validation failed for ${path.basename(inputFile)}: ${msg}`);
  }

  const extractor = new ASTExtractor();
  const converter = new KASTConverter();
  const postProcessor = new PostProcessor();
  const planationTool = new PlanationTool([
    ASTNodeTypes.VariableDeclaration,
    ASTNodeTypes.ArrayDeclaration,
    ASTNodeTypes.PointerDeclaration,
    ASTNodeTypes.ParameterDeclaration,
    ASTNodeTypes.AssignmentExpression,
    ASTNodeTypes.FunctionDeclaration,
    ASTNodeTypes.FunctionDefinition,
    ASTNodeTypes.StandardLibCall,
    ASTNodeTypes.UserDefinedCall,
    ASTNodeTypes.CastExpression,
    ASTNodeTypes.MemberAccess,
    ASTNodeTypes.PointerDereference,
    ASTNodeTypes.AddressOfExpression,
    ASTNodeTypes.ArraySubscriptExpression,
    ASTNodeTypes.BinaryExpression,
    ASTNodeTypes.UnaryExpression,
    ASTNodeTypes.SizeOfExpression,
    ASTNodeTypes.Identifier,
    ASTNodeTypes.Literal,
  ]);
  const treeToText = new TreeToText(["properties", "line_no", "code"]);

  // Build AST tree and KAST
  const ast: TreeNode[] = withContext("getAstTree", () => extractor.getAstTree(root.export));
  const converted = withContext("convertTree", () => converter.convertTree(ast));
  let kastResult: ASTNodes[] = withContext("removeInvalidNodes", () => postProcessor.removeInvalidNodes(converted));
  kastResult = withContext("addCodeProperties", () => postProcessor.addCodeProperties(kastResult, root));

  // Output paths inside the provided output directory
  const parsed = path.parse(inputFile);
  const astOutPath = path.join(outDir, `${parsed.name}_astTree${parsed.ext}`);
  const templateAstOutPath = path.join(outDir, `${parsed.name}_templateTree${parsed.ext}`);
  const textFile = path.join(outDir, `${parsed.name}_text.txt`);
  const flattenOutPath = path.join(outDir, `${parsed.name}_flatten.json`);

  // Write JSON outputs
  writeSingleJSON(ast, astOutPath);
  writeSingleJSON(kastResult, templateAstOutPath);

  // Write text view
  const textLines = kastResult.map((rootNode) => treeToText.convert(rootNode));
  await fs.promises.writeFile(textFile, textLines.join("\n\n"), "utf8");

  // Write flattened KAST
  const flatten = planationTool.flatten(kastResult);
  writeSingleJSON(flatten, flattenOutPath);

  // Simple verification statement
  console.log(
    `Generated: ${path.basename(astOutPath)}, ${path.basename(templateAstOutPath)}, ${path.basename(textFile)}, ${path.basename(flattenOutPath)}`
  );
}

function withContext<T>(fnName: string, fn: () => T): T {
  try {
    return fn();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`${fnName} failed: ${msg}`);
  }
}

function writeSingleJSON(item: ASTGraph[] | ASTNodes[] | TreeNode[], outPath: string): string {
  const [written] = writeJSONFiles([item], [outPath]);
  return written;
}

void (async () => {
  await main(inputArg, outDirArg);
})().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
