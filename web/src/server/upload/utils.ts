import type { GraphData, GraphUploadOptions } from "@ssat/prisma";
import { validateGraphData } from "@ssat/prisma";
import type { IASTResult } from "@ssat/core/types/ast";
import type { CPGGraphData } from "@ssat/core/types/cpg";
import type { IDFGGraph } from "@ssat/core/types/dfg";
import type { TemplateFlattenedGraph } from "@ssat/core/types/node";

export type RawGraphPayload = {
  type?: string;
  data?: unknown;
};

export interface RawGraphUploadOptions {
  sourceFile?: unknown;
  sourceLabel?: unknown;
  versionTag?: unknown;
  overwrite?: unknown;
  meta?: unknown;
}

const GRAPH_TYPE_ALIASES: Record<string, GraphData["type"]> = {
  ast: "AST",
  AST: "AST",
  cpg: "CPG",
  CPG: "CPG",
  dfg: "DFG",
  DFG: "DFG",
  template: "TEMPLATE",
  TEMPLATE: "TEMPLATE",
};

export function normalizeGraphType(input?: string): GraphData["type"] {
  if (!input) {
    throw new Error("Graph type is required");
  }

  const mapped = GRAPH_TYPE_ALIASES[input as keyof typeof GRAPH_TYPE_ALIASES];
  if (!mapped) {
    throw new Error(`Unsupported graph type: ${input}`);
  }

  return mapped;
}

export function buildGraphData(raw: RawGraphPayload): GraphData {
  const type = normalizeGraphType(raw.type);
  if (raw.data == null) {
    throw new Error("Graph data payload is required");
  }

  const graph = (() => {
    switch (type) {
      case "AST":
        return { type, data: raw.data as IASTResult[] };
      case "CPG":
        return { type, data: raw.data as CPGGraphData };
      case "DFG":
        return { type, data: raw.data as IDFGGraph };
      case "TEMPLATE":
        return { type, data: raw.data as TemplateFlattenedGraph };
      default: {
        const exhaustive: never = type;
        throw new Error(`Unhandled graph type ${(exhaustive as unknown) ?? "unknown"}`);
      }
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
    try {
      const parsed = JSON.parse(meta) as unknown;
      if (!parsed || typeof parsed !== "object") {
        throw new Error("Meta must be a JSON object");
      }
      return parsed as Record<string, unknown>;
    } catch (error) {
      throw new Error(`Unable to parse meta JSON: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  if (typeof meta === "object") {
    return meta as Record<string, unknown>;
  }

  throw new Error("Meta must be provided as an object or JSON string");
}

export function buildGraphUploadOptions(raw: RawGraphUploadOptions): GraphUploadOptions {
  const sourceFile = typeof raw.sourceFile === "string" ? raw.sourceFile.trim() : undefined;
  if (!sourceFile) {
    throw new Error("'sourceFile' is required in upload options");
  }

  const sourceLabel = typeof raw.sourceLabel === "string" ? raw.sourceLabel.trim() : undefined;
  const versionTag = typeof raw.versionTag === "string" ? raw.versionTag.trim() : undefined;
  const overwrite = typeof raw.overwrite === "boolean" ? raw.overwrite : raw.overwrite != null ? Boolean(raw.overwrite) : undefined;
  const meta = parseMeta(raw.meta);

  return {
    sourceFile,
    sourceLabel,
    versionTag,
    overwrite,
    meta,
  };
}

export interface GraphRequestPayload {
  graph: GraphData;
  options: GraphUploadOptions;
}

export function parseGraphRequestPayload(body: unknown): GraphRequestPayload {
  if (!body || typeof body !== "object") {
    throw new Error("Request body must be an object");
  }

  const record = body as Record<string, unknown>;
  const graphData = buildGraphData(record.graph as RawGraphPayload);
  const options = buildGraphUploadOptions((record.options ?? {}) as RawGraphUploadOptions);

  return { graph: graphData, options };
}

export function parseBulkGraphRequestPayload(body: unknown): GraphRequestPayload[] {
  if (!body || typeof body !== "object") {
    throw new Error("Request body must be an object");
  }

  const record = body as Record<string, unknown>;
  const items = record.graphs;

  if (!Array.isArray(items) || items.length === 0) {
    throw new Error("'graphs' must be a non-empty array");
  }

  return items.map((item, index) => {
    try {
      return parseGraphRequestPayload(item);
    } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      throw new Error(`Invalid entry at index ${index}: ${message}`);
    }
  });
}
