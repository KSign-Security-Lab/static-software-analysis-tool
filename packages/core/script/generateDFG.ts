import fs from "fs";
import path from "path";

import { validateCPGRoot } from "../cpg/validate/zod";
import { DFGBuilder } from "../dfg/DFGBuilder";
import DFGSync from "../dfg/DFGSync";
import { CPGRoot } from "../types/cpg";
import { IDFGGraph } from "../types/dfg";
import { TemplateFlattenedGraph } from "../types/node";
import { writeJSONFiles } from "../utils/json";

// Usage: tsx script/generateDFG.ts <input_json> [output_path_or_dir]
const args: string[] = process.argv.slice(2);
const firstArg: string | undefined = args[0];
const secondArg: string | undefined = args[1];
// If the second arg ends with .json, treat it as an exact output file path, otherwise as a directory
const isExactJsonPath = typeof secondArg === "string" && secondArg.toLowerCase().endsWith(".json");
const savePath: string = isExactJsonPath ? path.dirname(secondArg) : secondArg ? secondArg : firstArg ? path.dirname(firstArg) : "";

if (!firstArg) {
  console.error("Usage: tsx script/generateDFG.ts <input_json> [output_dir]");
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

function saveOutput(dfg: IDFGGraph, inputFile: string): void {
  const parsed = path.parse(inputFile);
  const outPath = isExactJsonPath ? secondArg : path.join(savePath, `${parsed.name}_dfg${parsed.ext}`);

  writeSingleJSON(dfg, outPath);
  console.log(`Generated: ${path.basename(outPath)}`);
}

async function readAST(inputFile: string): Promise<TemplateFlattenedGraph> {
  const raw = await fs.promises.readFile(inputFile, "utf8");
  return JSON.parse(raw) as TemplateFlattenedGraph;
}

function syncDFG(dfg: IDFGGraph, ast: TemplateFlattenedGraph): IDFGGraph {
  const dfgSync = new DFGSync(dfg, ast);
  return dfgSync.sync();
}

async function main(inputFile: string): Promise<void> {
  fs.mkdirSync(savePath, { recursive: true });

  const root = await readCPG(inputFile);

  verifyCPG(root, inputFile);

  const dfgBuilder = new DFGBuilder(root);
  const rawDFG = dfgBuilder.build();
  const ast = await readAST(inputFile);

  const syncedDFG = syncDFG(rawDFG, ast);

  saveOutput(syncedDFG, inputFile);
}

void (async () => {
  // after the early-exit guard, firstArg is defined
  await main(firstArg);
})().catch((err: unknown) => {
  console.error(err instanceof Error ? err.message : String(err));
  process.exit(1);
});
