import { generateAst, generateCpg, generateDfg, generateTemplate } from "@ssat/core/endpoint";
import { CPGRoot } from "@ssat/core/types/cpg";

import { SimpleLogger } from "./logger";
import { CliOptions, CliParser } from "./parser";

// Shared helpers
interface RootPackageJson {
  workspaces?: unknown;
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

async function main(): Promise<void> {
  const parser = new CliParser();
  const options: CliOptions = parser.parse();

  const logger = new SimpleLogger();

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

      // Start progress bar
      logger.startProgress(files.length);

      // Avoid aggregating all results in-memory to prevent OOM / Invalid string length errors
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        const isCFile = file.toLowerCase().endsWith(".c");
        let cpg: CPGRoot;
        if (isCFile) {
          cpg = await generateCpg(file);
        } else {
          const inputContentRaw = fs.readFileSync(file, "utf8");
          cpg = JSON.parse(inputContentRaw) as CPGRoot;
        }

        const filename = path.basename(file);

        logger.debug(`Processing file: ${filename}`);

        let result: unknown;
        switch (options.mode) {
          case "ast": {
            const template = generateTemplate(cpg);
            result = generateAst(template);
            break;
          }
          case "cpg": {
            // If input is CPG JSON, just echo normalized; if C source, already generated above
            result = cpg;
            break;
          }
          case "dfg": {
            const template = generateTemplate(cpg);
            const ast = generateAst(template);
            result = generateDfg(cpg, ast);
            break;
          }
          case "template":
            result = generateTemplate(cpg);
            break;
          default:
            throw new Error(`Unknown mode: ${String(options.mode)}`);
        }

        // Write per-file output preserving directory structure under outputPath
        try {
          const relative = path.relative(inputPath, file);
          const outPerFile = path.join(outputPath, path.dirname(relative), `${path.basename(file, path.extname(file))}_${options.mode}.json`);
          fs.mkdirSync(path.dirname(outPerFile), { recursive: true });
          fs.writeFileSync(outPerFile, JSON.stringify(result, null, 2));
        } catch {
          // ignore write errors for individual files; aggregate will still be produced
        }

        // Update progress
        logger.updateProgress(i + 1, { filename });
      }

      // Stop progress bar
      logger.stopProgress();

      // Skip writing a huge aggregate JSON to avoid memory/size limits
      const outputFile = path.join(outputPath, `${options.mode}_results.txt`);
      fs.mkdirSync(path.dirname(outputFile), { recursive: true });
      fs.writeFileSync(outputFile, `Processed ${String(files.length)} files. See per-file outputs under ${outputPath}.`);

      logger.info(`✓ Processing completed successfully`);
      logger.info(`Output written to: ${outputFile}`);
      logger.info(`Per-file outputs saved under: ${outputPath}`);
    } else {
      // Process single file
      const isCFile = inputPath.toLowerCase().endsWith(".c");
      let cpg: CPGRoot;
      if (isCFile) {
        cpg = await generateCpg(inputPath);
      } else {
        const inputContent = fs.readFileSync(inputPath, "utf8");
        cpg = JSON.parse(inputContent) as CPGRoot;
      }
      const filename = path.basename(inputPath);

      logger.debug(`Processing single file: ${filename}`);

      let result: unknown;
      switch (options.mode) {
        case "ast": {
          const template = generateTemplate(cpg);
          result = generateAst(template);
          break;
        }
        case "cpg": {
          result = cpg;
          break;
        }
        case "dfg": {
          const template = generateTemplate(cpg);
          const ast = generateAst(template);
          result = generateDfg(cpg, ast);
          break;
        }
        case "template":
          result = generateTemplate(cpg);
          break;
        default:
          throw new Error(`Unknown mode: ${String(options.mode)}`);
      }

      // Write output
      const outputFile = path.join(outputPath, `${options.mode}_result.json`);
      fs.mkdirSync(path.dirname(outputFile), { recursive: true });
      fs.writeFileSync(outputFile, JSON.stringify(result, null, 2));

      logger.info(`✓ Processing completed successfully`);
      logger.info(`Output written to: ${outputFile}`);
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
