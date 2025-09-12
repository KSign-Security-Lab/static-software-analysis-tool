import fs from "fs";
import path from "path";

import { validateCPGRoot } from "../cpg/validate/zod";
import { DFGBuilder } from "../dfg/DFGBuilder";
import { IASTResult } from "../types/ast";
import { CPGRoot } from "../types/cpg";
import { IDFGGraph } from "../types/dfg";
import { writeJSONFiles } from "../utils/json";

// Usage: tsx script/generateDFG.ts <input_cpg> <ast_file> <output_dir>
const args: string[] = process.argv.slice(2);
const cpgFile: string | undefined = args[0];
const astFile: string | undefined = args[1];
const outputDir: string | undefined = args[2];

if (!cpgFile || !astFile || !outputDir) {
  console.error("Usage: tsx script/generateDFG.ts <input_cpg> <ast_file> <output_dir>");
  console.error("  input_cpg: Path to CPG JSON file");
  console.error("  ast_file:  Path to AST JSON file");
  console.error("  output_dir: Output directory for DFG file");
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

function writeSingleJSON(item: unknown, outPath: string): string {
  const [written] = writeJSONFiles([item], [outPath]);
  return written;
}

function saveOutput(dfg: IDFGGraph[], cpgFile: string, outputDir: string): void {
  const parsed = path.parse(cpgFile);
  const outPath = path.join(outputDir, `${parsed.name}_dfg${parsed.ext}`);

  writeSingleJSON(dfg, outPath);
  console.log(`Generated: ${path.basename(outPath)}`);
}

async function readAST(astFile: string): Promise<IASTResult[]> {
  try {
    const raw = await fs.promises.readFile(astFile, "utf8");
    return JSON.parse(raw) as IASTResult[];
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    throw new Error(`Read/parse error for AST file ${path.basename(astFile)}: ${msg}`);
  }
}

async function main(cpgFile: string, astFile: string, outputDir: string): Promise<void> {
  // Ensure output directory exists
  fs.mkdirSync(outputDir, { recursive: true });

  // Verify files exist
  if (!fs.existsSync(cpgFile)) {
    throw new Error(`CPG file not found: ${cpgFile}`);
  }
  if (!fs.existsSync(astFile)) {
    throw new Error(`AST file not found: ${astFile}`);
  }

  console.log(`Processing CPG: ${path.basename(cpgFile)}`);
  console.log(`Using AST: ${path.basename(astFile)}`);
  console.log(`Output directory: ${outputDir}`);

  // Read and validate CPG
  const root = await readCPG(cpgFile);
  verifyCPG(root, cpgFile);

  // Read AST file
  const ast = await readAST(astFile);

  // Generate DFG using CPG + AST
  const dfgBuilder = new DFGBuilder();
  const dfg = dfgBuilder.build(root, ast);

  // Save DFG output
  saveOutput(dfg, cpgFile, outputDir);
}

void (async () => {
  // All arguments are validated above
  await main(cpgFile, astFile, outputDir);
})().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
