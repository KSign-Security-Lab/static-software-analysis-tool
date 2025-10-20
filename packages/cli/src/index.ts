import type { IASTResult } from "@ssat/core/types/ast";
import type { TemplateNodes } from "@ssat/core/types/node";

import { recursivelyGetFunctionsFromTemplate } from "@ssat/core/ast/utils";
import { generateAst, generateCpg, generateDfg, generateTemplate } from "@ssat/core/endpoint";
import { CPGRoot } from "@ssat/core/types/cpg";
import { IDFGGraph } from "@ssat/core/types/dfg";

import { SimpleLogger } from "./logger";
import { CliOptions, CliParser } from "./parser";

// Shared helpers
interface RootPackageJson {
  workspaces?: unknown;
}

// Common utility: sanitize filename token
function sanitizeToken(s: string): string {
  return s.replace(/[^a-zA-Z0-9_-]+/g, "_").slice(0, 100);
}

function extractNameFromCode(code: string | undefined, fallback: string): string {
  let m = code?.split("<entry:").at(-1);
  m = m?.split("_").at(-1);
  m = m?.split("(").at(-1);
  m = m?.split(")").at(-1);
  m = m?.split("[").at(-1);
  m = m?.split("]").at(-1);
  m = m?.split("{").at(-1);
  m = m?.split("}").at(-1);
  m = m?.split(":").at(-1);
  m = m?.split(";").at(-1);
  m = m?.split(",").at(-1);
  m = m?.split(".").at(-1);
  m = m?.split("?").at(-1);
  m = m?.split("!").at(-1);
  m = m?.split("|").at(-1);
  m = m?.split("&").at(-1);
  m = m?.split("^").at(-1);
  m = m?.split("~").at(-1);
  m = m?.split("`").at(-1);
  m = m?.split("'").at(-1);
  m = m?.split('"').at(-1);
  m = m?.split(" ").at(-1);
  m = m?.split("\n").at(-1);
  m = m?.split("\t").at(-1);
  m = m?.split("\r").at(-1);
  m = m?.split("\b").at(-1);
  m = m?.split("\f").at(-1);
  return sanitizeToken(m ?? fallback);
}

// Common utility: save per-function outputs for AST and TemplateFunctions modes
function savePerFunction(
  mode: "ast" | "template-functions" | "dfg" | "full",
  result: unknown,
  filePath: string,
  outDir: string,
  path: typeof import("path"),
  fs: typeof import("fs")
): void {
  const base = path.basename(filePath, path.extname(filePath));
  switch (mode) {
    case "ast": {
      const astArray = result as IASTResult[];
      for (let idx = 0; idx < astArray.length; idx++) {
        const funcName = extractNameFromCode(astArray[idx].nodes[0].code, `func_${String(idx)}`);
        const perFuncFile = `${base}_${funcName}_${mode}.json`;
        const perFuncPath = path.join(outDir, perFuncFile);
        fs.writeFileSync(perFuncPath, JSON.stringify(astArray[idx], null, 2));
      }
      return;
    }
    case "dfg":
    case "template-functions": {
      const funcs = result as TemplateNodes[] | IDFGGraph[];
      for (let i = 0; i < funcs.length; i++) {
        const fn = funcs[i];
        let fnName = `func_${String(i)}`;
        if (mode === "dfg") {
          const nodes = (fn as IDFGGraph).nodes;
          const debugCode = nodes.length > 0 && typeof nodes[0].debug?.callName === "string" ? nodes[0].debug.callName : undefined;
          fnName = extractNameFromCode(debugCode, fnName);
        } else {
          const name = (fn as TemplateNodes).name;
          fnName = extractNameFromCode(name, fnName);
        }
        const perFuncFile = `${base}_${fnName}_${mode}.json`;
        const perFuncPath = path.join(outDir, perFuncFile);
        fs.writeFileSync(perFuncPath, JSON.stringify(funcs[i], null, 2));
      }
      return;
    }
    case "full": {
      const fullResult = result as { ast: IASTResult[]; dfg: IDFGGraph[] };
      if (fullResult.ast.length !== fullResult.dfg.length) {
        throw new Error("AST and DFG results must have the same length");
      }
      for (let idx = 0; idx < fullResult.ast.length; idx++) {
        const functionNode = fullResult.ast[idx].nodes[0];
        const funcName = extractNameFromCode(functionNode.code, `func_${String(idx)}`);
        const perFuncFile = `${base}_${funcName}_${mode}.json`;
        const perFuncPath = path.join(outDir, perFuncFile);
        const saveObj = {
          file: funcName,
          label: funcName.includes("bad") ? 1 : 0,
          ast_result: fullResult.ast[idx],
          dfg_result: fullResult.dfg[idx],
        };
        fs.writeFileSync(perFuncPath, JSON.stringify(saveObj, null, 2));
      }
      return;
    }
    default:
      throw new Error(`Unknown mode: ${String(mode)}`);
  }
}

const findMonorepoRoot = async (startDir: string): Promise<string> => {
  const path = await import("path");
  const fs = await import("fs");
  let currentDir = startDir;
  while (currentDir !== path.dirname(currentDir)) {
    const pkgPath = path.join(currentDir, "package.json");
    try {
      const pkgJson = JSON.parse(fs.readFileSync(pkgPath, "utf8")) as RootPackageJson;
      if (Array.isArray(pkgJson.workspaces)) {
        return currentDir;
      }
    } catch {
      // ignore
    }
    currentDir = path.dirname(currentDir);
  }
  return startDir;
};

const resolveInputPath = async (p: string): Promise<string> => {
  const path = await import("path");
  const fs = await import("fs");
  if (path.isAbsolute(p)) return p;
  const fromCwd = path.resolve(process.cwd(), p);
  if (fs.existsSync(fromCwd)) return fromCwd;
  const workspaceRoot = await findMonorepoRoot(process.cwd());
  const fromRoot = path.resolve(workspaceRoot, p);
  if (fs.existsSync(fromRoot)) return fromRoot;
  return fromCwd;
};

const collectFilesRecursively = (
  dir: string,
  predicate: (filePath: string) => boolean,
  fs: typeof import("fs"),
  path: typeof import("path")
): string[] => {
  const files: string[] = [];
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectFilesRecursively(fullPath, predicate, fs, path));
    } else if (entry.isFile() && predicate(fullPath)) {
      files.push(fullPath);
    }
  }
  return files;
};

// Thread-safe progress tracker for parallel processing
class ProgressTracker {
  private completed = 0;
  private total: number;
  private logger: SimpleLogger;
  private lastUpdate = 0;
  private updateInterval = 100; // Update every 100ms max

  constructor(total: number, logger: SimpleLogger) {
    this.total = total;
    this.logger = logger;
  }

  increment(filename: string) {
    this.completed++;
    const now = Date.now();

    // Always update on the last item
    if (this.completed === this.total) {
      this.logger.updateProgress(this.completed, { filename });
      this.lastUpdate = now;
    }
    // Throttle updates to avoid overwhelming the progress bar
    else if (now - this.lastUpdate > this.updateInterval) {
      this.logger.updateProgress(this.completed, { filename });
      this.lastUpdate = now;
    }
  }

  getCompleted(): number {
    return this.completed;
  }
}

// Parallel processing function that uses existing processSingleFile
async function processFilesInParallel(
  files: string[],
  inputRoot: string,
  outputRoot: string,
  options: CliOptions,
  logger: SimpleLogger,
  path: typeof import("path"),
  fs: typeof import("fs"),
  maxWorkers: number
): Promise<void> {
  const workers = Math.min(maxWorkers, files.length);

  // Create thread-safe progress tracker
  const progressTracker = new ProgressTracker(files.length, logger);

  // Simple concurrency limiter using Promise.all with chunks
  const chunkSize = Math.ceil(files.length / workers);
  const chunks: string[][] = [];

  for (let i = 0; i < files.length; i += chunkSize) {
    chunks.push(files.slice(i, i + chunkSize));
  }

  // Process chunks in parallel, but files within each chunk sequentially
  // This gives us true parallelism across chunks while avoiding overwhelming the system
  const processChunk = async (chunk: string[]) => {
    for (const file of chunk) {
      try {
        await processSingleFile(file, inputRoot, outputRoot, options, logger, path, fs);
        progressTracker.increment(path.basename(file));
      } catch (error) {
        // Log error but continue processing other files
        logger.error(`Failed to process ${file}: ${error instanceof Error ? error.message : String(error)}`);
        progressTracker.increment(path.basename(file));
      }
    }
  };

  // Process all chunks in parallel
  await Promise.all(chunks.map(processChunk));

  // Ensure final progress update
  if (progressTracker.getCompleted() < files.length) {
    logger.updateProgress(files.length, { filename: "completed" });
  }
}

// New: common single-file processor
async function processSingleFile(
  filePath: string,
  inputRoot: string,
  outputRoot: string,
  options: CliOptions,
  logger: SimpleLogger,
  path: typeof import("path"),
  fs: typeof import("fs")
): Promise<void> {
  const isCFile = filePath.toLowerCase().endsWith(".c");
  let cpg: CPGRoot;
  if (isCFile) {
    cpg = await generateCpg(filePath, "file");
  } else {
    const inputContent = fs.readFileSync(filePath, "utf8");
    cpg = JSON.parse(inputContent) as CPGRoot;
  }

  // Pre-compute output directory for this file
  const relative = path.relative(inputRoot, filePath);
  const outDir = path.join(outputRoot, path.dirname(relative));
  fs.mkdirSync(outDir, { recursive: true });

  let result: unknown;
  switch (options.mode) {
    case "ast": {
      const template = generateTemplate(cpg);
      result = await generateAst(template);
      break;
    }
    case "cpg": {
      result = cpg;
      break;
    }
    case "dfg": {
      const template = generateTemplate(cpg);
      const ast = await generateAst(template);
      const dfg = generateDfg(cpg, ast);
      result = dfg;
      break;
    }
    case "full": {
      const template = generateTemplate(cpg);
      const ast = await generateAst(template);
      const dfg = generateDfg(cpg, ast);
      result = { ast, dfg };
      break;
    }
    case "template":
      result = generateTemplate(cpg);
      break;
    case "template-functions": {
      // Generate template and collect function nodes using shared utils
      const template = generateTemplate(cpg);
      const roots: TemplateNodes[] = Array.isArray(template) ? template : [];
      const functions = recursivelyGetFunctionsFromTemplate(roots);
      result = functions;
      break;
    }
    default:
      throw new Error(`Unknown mode: ${String(options.mode)}`);
  }

  // Common per-file writer
  if (options.mode === "ast" || options.mode === "template-functions" || options.mode === "dfg" || options.mode === "full") {
    savePerFunction(options.mode, result, filePath, outDir, path, fs);
    return;
  }

  // Default single-output writer
  const perFileOutput = path.join(outDir, `${path.basename(filePath, path.extname(filePath))}_${options.mode}.json`);
  fs.writeFileSync(perFileOutput, JSON.stringify(result, null, 2));
  // logger.info("✓ Processing completed successfully");
  // logger.info(`Output written to: ${perFileOutput}`);
}

async function main(): Promise<void> {
  const parser = new CliParser();
  const options: CliOptions = parser.parse();

  const logger = new SimpleLogger(options.debug);

  // Set up logging level based on environment
  // (Simple logger handles this internally)

  logger.info("Static Software Analysis Tool (SSAT) v2.4.3");
  logger.info(`Mode: ${options.mode}`);
  logger.info(`Input: ${options.data}`);

  // Determine output path (resolve relative to workspace root for consistent outputs)
  const path = await import("path");
  const fs = await import("fs");
  const workspaceRoot = await findMonorepoRoot(process.cwd());
  const rawOutput = options.output ?? `result/${options.mode}_${String(Date.now())}`;
  const outputPath = path.isAbsolute(rawOutput) ? rawOutput : path.resolve(workspaceRoot, rawOutput);
  logger.info(`Output: ${outputPath}`);

  try {
    // Read input file or directory

    const inputPath = await resolveInputPath(options.data);
    const stat = fs.statSync(inputPath);

    if (stat.isDirectory()) {
      // Collect all .c and .json files recursively
      const files = collectFilesRecursively(inputPath, (filePath) => filePath.endsWith(".c") || filePath.endsWith(".json"), fs, path);

      if (files.length === 0) {
        throw new Error(`No .c or .json files found in directory: ${inputPath}`);
      }

      logger.info(`Processing ${String(files.length)} files in directory`);

      // Parse workers option and choose processing method
      const workers = parseInt(options.workers ?? "1", 10);

      // For CPG mode, always use 1 worker (sequential) to avoid Docker conflicts
      const effectiveWorkers = options.mode === "cpg" ? 1 : workers;

      if (effectiveWorkers > 1) {
        // Start progress bar for parallel processing first
        logger.info(`Using ${String(effectiveWorkers)} parallel workers`);

        logger.startProgress(files.length);

        // Small delay to ensure progress bar has time to render
        await new Promise((resolve) => setTimeout(resolve, 200));

        // Log worker info without stopping progress bar

        // Use parallel processing
        await processFilesInParallel(files, inputPath, outputPath, options, logger, path, fs, effectiveWorkers);
      } else {
        // Start progress bar for sequential processing
        logger.startProgress(files.length);

        // Use sequential processing (original behavior)
        for (let i = 0; i < files.length; i++) {
          const file = files[i];
          await processSingleFile(file, inputPath, outputPath, options, logger, path, fs);
          // Update progress
          logger.updateProgress(i + 1, { filename: path.basename(file) });
        }
      }

      // Stop progress bar
      logger.stopProgress();

      // Skip writing a huge aggregate JSON to avoid memory/size limits
      const outputFile = path.join(outputPath, `${options.mode}_results.txt`);
      fs.mkdirSync(path.dirname(outputFile), { recursive: true });
      fs.writeFileSync(outputFile, `Processed ${String(files.length)} files. See per-file outputs under ${outputPath}.`);

      logger.info("✓ Processing completed successfully");
      logger.info(`Output written to: ${outputFile}`);
      logger.info(`Per-file outputs saved under: ${outputPath}`);
    } else {
      // Process single file via common function
      await processSingleFile(inputPath, workspaceRoot, outputPath, options, logger, path, fs);
    }

    process.exit(0);
  } catch (error: unknown) {
    logger.error(`✗ Processing failed: ${error instanceof Error ? error.message : String(error)}`);
    process.exit(1);
  }
}

// Handle uncaught errors
process.on("uncaughtException", (error) => {
  console.error("Uncaught Exception:", error);
  process.exit(1);
});

process.on("unhandledRejection", (reason: unknown, promise: Promise<unknown>) => {
  console.error("Unhandled Rejection at:", promise, "reason:", reason);
  process.exit(1);
});

// Run the main function
main().catch((error: unknown) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
