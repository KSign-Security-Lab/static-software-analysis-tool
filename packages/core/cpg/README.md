# CPG Generation - Technical Documentation

## Table of Contents

1. [Joern Foundations](#joern-foundations)
2. [CLI Flow Overview](#cli-flow-overview)
3. [File Resolution and Parallelism](#file-resolution-and-parallelism)
4. [Single File Processing](#single-file-processing)
5. [Core Generator Internals](#core-generator-internals)
6. [Validation and Error Handling](#validation-and-error-handling)
7. [Outputs and Downstream Consumers](#outputs-and-downstream-consumers)

---

## Joern Foundations

The Code Property Graph (CPG) for SSAT is produced by [Joern](https://joern.io/), a static analysis platform that provides `joern-parse` (to build `cpg.bin`) and `joern-export` (to serialize the graph). SSAT wraps those binaries in the `CPGGenerator` class inside `packages/core/cpg/CPGGenerator.ts`.

Two execution strategies exist:

- **Standalone mode** runs Joern directly on the host (useful for local development or CI runners that already have `joern-parse` on the `PATH`).
- **Docker mode** targets a long-lived container (`ssat-joern-${user}`) and mirrors sources into `workspace/` before invoking Joern inside the container. This avoids installing Joern locally and provides isolation for multiple concurrent runs.

Both strategies follow the same high-level sequence:

1. Normalize the input (either C source content or a `.c` file on disk).
2. Run `joern-parse` to build `cpg.bin`.
3. Run `joern-export --repr=all --format=graphson` to obtain GraphSON output.
4. Merge JSON fragments (when `joern-export` writes to `out/*.json`) into a single `ICPGRootExport`.

```typescript
// packages/core/cpg/CPGGenerator.ts
const parse = spawn("joern-parse", [sourceFile], { cwd: tmpDir });
// ...
const exportCmd = spawn("joern-export", ["--repr=all", "--format=graphson"], { cwd: tmpDir });
```

Joern therefore remains the canonical source of truth for CPG data, while SSAT layers validation, normalization, and downstream transformations on top.

---

## CLI Flow Overview

The command-line interface in `packages/cli/src/index.ts` orchestrates end-to-end processing. The CLI exposes several modes (`cpg`, `template`, `ast`, `dfg`, `full`, `template-functions`) and delegates to the core endpoints as needed. Regardless of mode, every `.c` source first becomes a CPG by calling `generateCpg` from `@ssat/core/endpoint`.

High-level steps executed by `main()`:

1. Parse CLI flags via `CliParser`.
2. Normalize input/output paths relative to the monorepo root (`findMonorepoRoot`, `resolveInputPath`).
3. Collect all `.c` or `.json` files (recursive when the input is a directory).
4. Process files sequentially or in parallel depending on the `--workers` option and mode.
5. Persist results (per-function or per-file JSON) in the resolved output directory.

Concurrency is coordinated by `processFilesInParallel`, which chunks the workload, tracks progress, and calls `processSingleFile` for each source. In `cpg` mode the CLI intentionally forces `workers=1` to avoid racing Joern Docker instances.

---

## File Resolution and Parallelism

Before any CPG work begins, the CLI resolves input paths and collects the relevant files:

```typescript
// packages/cli/src/index.ts
const inputPath = await resolveInputPath(options.data);
const files = collectFilesRecursively(inputPath, (filePath) => filePath.endsWith(".c") || filePath.endsWith(".json"), fs, path);
```

- Relative paths are resolved against both the current working directory and the monorepo root (useful when running `pnpm cli -- data/samples` from sub-packages).
- JSON inputs are treated as pre-generated CPGs and bypass Joern execution.
- When multiple files exist, `processFilesInParallel` slices the list into chunks (bounded by `--workers`) and streams progress updates via `SimpleLogger`.

---

## Single File Processing

Every file—collected via directory traversal or provided explicitly—is transformed inside `processSingleFile`. This is the connective tissue between the CLI and the core endpoint.

```typescript
// packages/cli/src/index.ts (simplified)
async function processSingleFile(...) {
  const isCFile = filePath.toLowerCase().endsWith(".c");
  let cpg: CPGRoot;
  if (isCFile) {
    cpg = await generateCpg(filePath, "file");
  } else {
    cpg = JSON.parse(fs.readFileSync(filePath, "utf8"));
  }

  switch (options.mode) {
    case "cpg":
      result = cpg;
      break;
    case "template":
      result = generateTemplate(cpg);
      break;
    case "ast":
      result = await generateAst(generateTemplate(cpg));
      break;
    case "dfg":
      result = generateDfg(cpg, await generateAst(generateTemplate(cpg)));
      break;
    case "full":
      // Produces paired AST + DFG per function
      break;
    case "template-functions":
      // Extracts per-function subtrees
      break;
    default:
      throw new Error(`Unknown mode: ${String(options.mode)}`);
  }
}
```

Key points:

- `.c` inputs flow through `generateCpg(filePath, "file")`, which boots the Joern-backed generator and validates the result.
- `.json` inputs are expected to already contain CPG GraphSON and are parsed directly—useful for replaying previously captured graphs.
- The CLI reuses the same `CPGRoot` for all downstream steps in the file (avoiding redundant Joern calls when generating AST/DFG artifacts).
- Per-function writers (`savePerFunction`) are invoked for modes that emit multiple outputs (`ast`, `dfg`, `template-functions`, `full`).

---

## Core Generator Internals

`generateCpg` (exported from `packages/core/endpoint/index.ts`) is intentionally thin. It instantiates `CPGGenerator`, converts the requested file (via Docker by default), validates the resulting graph, and returns a `CPGRoot`.

```typescript
// packages/core/endpoint/index.ts
export async function generateCpg(filePath: string, type?: "file" | "string"): Promise<CPGRoot> {
  const cpgGenerator = new CPGGenerator();
  const cpgStandalone = await cpgGenerator.convertToCPGDocker(
    filePath,
    type && type === "file" ? { filename: filePath, isFilePath: true } : undefined
  );
  validateCPGRoot([cpgStandalone.cpgData.export]);
  return cpgStandalone.cpgData;
}
```

### Docker-backed Workflow

Most CLI executions rely on `convertToCPGDocker`, which handles workspace management and container interaction:

```typescript
// packages/core/cpg/CPGGenerator.ts
const CONTAINER_NAME = `ssat-joern-${USERNAME}`;
const workspaceDir = path.join(projectRoot, "workspace");
await fs.copyFile(sourceFile, workspaceSourceFile);
// ...
const parse = spawn("docker", ["exec", CONTAINER_NAME, "/opt/joern/joern-cli/bin/joern-parse", `/workspace/${relativePath}`]);
```

Highlights:

- Inputs are copied beneath `workspace/` inside the monorepo so that the Docker container can access them via a bind mount.
- Prior `cpg.bin` and `out/` artifacts are deleted both locally and inside the container to avoid stale outputs.
- The same two-step Joern process (parse/export) runs inside the container.
- When `joern-export` writes JSON files into `workspace/out`, SSAT merges them and returns a single `ICPGRootExport`.

### Standalone Workflow

`convertToCPGStandalone` mirrors the logic but uses host binaries instead of Docker. It creates temporary directories in the system `tmpdir`, writes the source, runs Joern, and deletes the directory afterwards. This path is convenient for tests or specialized deployments where Docker is unavailable.

---

## Validation and Error Handling

Multiple safeguards ensure the generated CPG is valid before downstream systems consume it:

- **Zod Validation**: `validateCPGRoot` enforces shape and required properties for the `CPGRoot.export` object.
- **Method Count**: `CPGGenerator.countMethods` inspects the GraphSON payload and tallies methods for quick sanity checks/logging.
- **Error Context**: Any failure in `joern-parse`, `joern-export`, Docker exec, or file I/O is wrapped with descriptive messages (e.g., `"cpg.bin not found after joern-parse"`).
- **CLI Resilience**: When batch-processing directories, exceptions in `processSingleFile` are caught per file so the rest of the queue continues processing.

These layers help pinpoint whether an issue stems from Joern itself, Docker connectivity, or malformed input.

---

## Outputs and Downstream Consumers

Once a `CPGRoot` exists, the CLI can:

- Emit the raw GraphSON (`--mode cpg`).
- Convert to template trees (`generateTemplate`), flatten graphs, or extract per-function slices.
- Feed templates into the Python-based AST extractor (`generateAst`) and subsequently into the DFG builder (`generateDfg`).
- Write per-function JSONs that combine AST + DFG (`--mode full`) with helpful metadata such as inferred labels.

Because everything starts with a validated CPG, other subsystems (Template, AST, DFG, graph-based analytics) can trust the structure and focus on higher-level transformations.

---

## Summary

1. **Joern remains the CPG authority**. SSAT delegates parsing/exporting to Joern (host or Docker) and focuses on validation plus orchestration.
2. **The CLI coordinates the pipeline**. It normalizes paths, batches files, and invokes `generateCpg` exactly once per `.c` file before branching into other modes.
3. **`CPGGenerator` handles the heavy lifting**. It prepares workspaces, runs Joern, merges outputs, and exposes a clean `CPGRoot` for the rest of the system.
4. **Robust error handling prevents silent failures**. Descriptive exceptions and per-file try/catch blocks isolate issues without halting entire batches.

Use this document as the starting point whenever you need to troubleshoot CPG generation, understand how Joern integrates with SSAT, or extend the CLI pipeline.
