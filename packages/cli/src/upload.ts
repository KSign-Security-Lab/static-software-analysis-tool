import type { IASTResult } from "@ssat/core/types/ast";
import type { CPGGraphData } from "@ssat/core/types/cpg";
import type { IDFGGraph } from "@ssat/core/types/dfg";
import type { TemplateFlattenedGraph } from "@ssat/core/types/node";

import { databaseService, type GraphData, type GraphUploadOptions, uploadGraph, uploadGraphsFromDirectory, validateGraphData } from "@ssat/prisma";
import { Command } from "commander";
import fs from "node:fs/promises";
import path from "node:path";

const GRAPH_TYPE_ALIASES: Partial<Record<string, GraphData["type"]>> = {
  ast: "AST",
  AST: "AST",
  cpg: "CPG",
  CPG: "CPG",
  dfg: "DFG",
  DFG: "DFG",
  template: "TEMPLATE",
  TEMPLATE: "TEMPLATE",
};

function normalizeGraphType(input?: string): GraphData["type"] {
  if (!input) {
    throw new Error("Graph type is required");
  }

  const mapped = GRAPH_TYPE_ALIASES[input];
  if (!mapped) {
    throw new Error(`Unsupported graph type: ${input}`);
  }

  return mapped;
}

function buildGraphData(type: string, data: unknown): GraphData {
  const graphType = normalizeGraphType(type);

  const graph = (() => {
    switch (graphType) {
      case "AST":
        return { type: graphType, data: data as IASTResult[] };
      case "CPG":
        return { type: graphType, data: data as CPGGraphData };
      case "DFG":
        return { type: graphType, data: data as IDFGGraph };
      case "TEMPLATE":
        return { type: graphType, data: data as TemplateFlattenedGraph };
      default:
        // This path should be unreachable because all GraphData["type"] cases are covered
        throw new Error("Unhandled graph type");
    }
  })();

  const validation = validateGraphData(graph);
  if (!validation.valid) {
    throw new Error(`Invalid graph payload: ${validation.errors.join("; ")}`);
  }

  return graph;
}

function parseMeta(meta: unknown): Record<string, unknown> | undefined {
  if (meta == null) {
    return undefined;
  }

  if (typeof meta === "string" && meta.trim().length === 0) {
    return undefined;
  }

  if (typeof meta === "string") {
    const parsed = JSON.parse(meta) as unknown;
    if (!parsed || typeof parsed !== "object") {
      throw new Error("Meta JSON must describe an object");
    }
    return parsed as Record<string, unknown>;
  }

  if (typeof meta === "object") {
    return meta as Record<string, unknown>;
  }

  throw new Error("Meta must be provided as a JSON string or object");
}

const program = new Command("ssat-upload");

program.description("Upload SSAT graph artifacts to the database");

program
  .command("graph")
  .description("Upload a single graph JSON file")
  .requiredOption("--type <type>", "Graph type (AST, CPG, DFG, TEMPLATE)")
  .requiredOption("-i, --input <file>", "Path to graph JSON file")
  .option("-s, --source-file <value>", "Value to store in sourceFile (defaults to input path)")
  .option("--source-label <value>", "Optional source label")
  .option("--version-tag <value>", "Optional version tag")
  .option("--meta <json>", "Optional metadata JSON string")
  .option("--overwrite", "Replace existing graph with same content hash")
  .action(async (options: Record<string, unknown>) => {
    const inputPath = options.input as string;
    const rawType = options.type as string;

    if (!inputPath) {
      throw new Error("Input file path is required");
    }

    const absolutePath = path.resolve(inputPath);
    const fileContents = await fs.readFile(absolutePath, "utf8");
    const parsed = JSON.parse(fileContents) as unknown;

    const graph = buildGraphData(rawType, parsed);
    const uploadOptions: GraphUploadOptions = {
      sourceFile: (options.sourceFile as string | undefined) ?? absolutePath,
      sourceLabel: typeof options.sourceLabel === "string" ? options.sourceLabel : undefined,
      versionTag: typeof options.versionTag === "string" ? options.versionTag : undefined,
      overwrite: options.overwrite != null ? Boolean(options.overwrite) : undefined,
      meta: parseMeta(options.meta),
    };
    await databaseService.connect();
    try {
      const result = await uploadGraph(graph, uploadOptions, databaseService);

      const status = result.isNew ? "created" : "existing";
      console.log(`✅ Upload ${status}: id=${result.graph.id}, nodes=${String(result.nodeCount)}, edges=${String(result.edgeCount)}`);
    } finally {
      await databaseService.disconnect();
    }
  });

program
  .command("bulk")
  .description("Upload every JSON file in a directory")
  .requiredOption("--type <type>", "Graph type (AST, CPG, DFG, TEMPLATE)")
  .requiredOption("-d, --directory <path>", "Directory containing JSON files")
  .option("--version-tag <value>", "Version tag applied to each upload")
  .option("--source-label <value>", "Source label applied to each upload")
  .option("--meta <json>", "Metadata JSON applied to each upload")
  .option("--overwrite", "Replace existing graphs if they already exist")
  .action(async (options: Record<string, unknown>) => {
    const directory = options.directory as string;
    const rawType = options.type as string;

    if (!directory) {
      throw new Error("Directory path is required");
    }

    const graphType = normalizeGraphType(rawType);
    const uploadOptions: Omit<GraphUploadOptions, "sourceFile"> = {
      sourceLabel: typeof options.sourceLabel === "string" ? options.sourceLabel : undefined,
      versionTag: typeof options.versionTag === "string" ? options.versionTag : undefined,
      overwrite: options.overwrite != null ? Boolean(options.overwrite) : undefined,
      meta: parseMeta(options.meta),
    };

    await databaseService.connect();
    try {
      const result = await uploadGraphsFromDirectory(directory, graphType, uploadOptions, databaseService);

      console.log(`✅ Bulk upload complete: ${String(result.successful)} succeeded, ${String(result.failed)} failed`);
      if (result.errors.length > 0) {
        for (const item of result.errors) {
          console.error(`  • ${item.file}: ${item.error}`);
        }
      }
    } finally {
      await databaseService.disconnect();
    }
  });

async function main() {
  try {
    await program.parseAsync(process.argv);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    console.error(`❌ ${message}`);
    process.exitCode = 1;
  }
}

void main();
