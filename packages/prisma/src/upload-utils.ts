import fs from 'node:fs/promises';
import path from 'node:path';

import { GraphType, type Graph } from '@prisma/client';

import type {
  GraphData,
  GraphUploadOptions,
  DatabaseUploadResult,
  BulkUploadResult,
} from './types';
import { DatabaseService, databaseService } from './services/database-service';
// Import core types directly - no duplication
import type {
  IASTGraph,
  CPGGraphData,
  IDFGGraph,
  TemplateFlattenedGraph,
} from '@ssat/core';

interface CountSummary {
  nodeCount: number;
  edgeCount: number;
}

function computeCountsFromData(graphData: GraphData): CountSummary {
  switch (graphData.type) {
    case 'AST':
      return {
        nodeCount: graphData.data.ast_result.nodes.length,
        edgeCount:
          graphData.data.ast_result.edges_ast_pc.length +
          graphData.data.ast_result.edges_ast_sb.length +
          graphData.data.ast_result.edges_ast_guard.length,
      };
    case 'CPG':
      return {
        nodeCount: graphData.data.vertices.length,
        edgeCount: graphData.data.edges.length,
      };
    case 'DFG':
      return {
        nodeCount: graphData.data.nodes.length,
        edgeCount: graphData.data.edges.length,
      };
    case 'TEMPLATE':
      return {
        nodeCount: graphData.data.nodes.length,
        edgeCount: graphData.data.edges.length,
      };
    default: {
      const exhaustive: never = graphData;
      throw new Error(
        `Unsupported graph type ${(exhaustive as Record<string, unknown>).type}`
      );
    }
  }
}

function extractCountsFromMeta(meta: unknown): Partial<CountSummary> {
  if (meta && typeof meta === 'object') {
    const record = meta as Record<string, unknown>;
    const nodeCount =
      typeof record.nodeCount === 'number' ? record.nodeCount : undefined;
    const edgeCount =
      typeof record.edgeCount === 'number' ? record.edgeCount : undefined;
    return { nodeCount, edgeCount };
  }

  return {};
}

async function resolveExistingCounts(
  service: DatabaseService,
  graph: Graph
): Promise<CountSummary> {
  const metaCounts = extractCountsFromMeta(graph.meta);

  const nodeCount =
    metaCounts.nodeCount ??
    (await service.client.aSTNode.count({
      where: { graphId: graph.id },
    })) +
      (await service.client.dFGNode.count({
        where: { graphId: graph.id },
      }));

  const edgeCount =
    metaCounts.edgeCount ??
    (await service.client.aSTEdge.count({
      where: { graphId: graph.id },
    })) +
      (await service.client.dFGEdge.count({
        where: { graphId: graph.id },
      }));

  return { nodeCount, edgeCount };
}

export async function uploadGraph(
  graphData: GraphData,
  options: GraphUploadOptions,
  service: DatabaseService = databaseService
): Promise<DatabaseUploadResult> {
  const validation = validateGraphData(graphData);
  if (!validation.valid) {
    throw new Error(`Invalid graph data: ${validation.errors.join('; ')}`);
  }

  const countsFromData = computeCountsFromData(graphData);
  const meta = options.meta ?? {};

  switch (graphData.type) {
    case 'AST': {
      const existingGraph = await service.client.graph.findFirst({
        where: {
          type: GraphType.AST,
          sourceFile: options.sourceFile,
          ...(options.sourceLabel ? { sourceLabel: options.sourceLabel } : {}),
        },
      });

      if (existingGraph) {
        if (options.overwrite) {
          await service.deleteGraph(existingGraph.id);
        } else {
          const counts = await resolveExistingCounts(service, existingGraph);
          return {
            graph: existingGraph,
            nodeCount: counts.nodeCount,
            edgeCount: counts.edgeCount,
            isNew: false,
          };
        }
      }

      const graph = await service.uploadASTGraph(
        graphData.data,
        options.sourceFile,
        options.versionTag,
        meta,
        options.sourceLabel
      );

      return {
        graph,
        nodeCount: countsFromData.nodeCount,
        edgeCount: countsFromData.edgeCount,
        isNew: true,
      };
    }

    case 'CPG': {
      const existingGraph = await service.client.graph.findFirst({
        where: {
          type: GraphType.CPG,
          sourceFile: options.sourceFile,
        },
      });

      if (existingGraph) {
        if (options.overwrite) {
          await service.deleteGraph(existingGraph.id);
        } else {
          const counts = await resolveExistingCounts(service, existingGraph);
          return {
            graph: existingGraph,
            nodeCount: counts.nodeCount,
            edgeCount: counts.edgeCount,
            isNew: false,
          };
        }
      }

      const graph = await service.uploadCPGGraph(
        graphData.data,
        options.sourceFile,
        options.versionTag,
        meta
      );

      return {
        graph,
        nodeCount: countsFromData.nodeCount,
        edgeCount: countsFromData.edgeCount,
        isNew: true,
      };
    }

    case 'DFG': {
      const existingGraph = await service.client.graph.findFirst({
        where: {
          type: GraphType.DFG,
          sourceFile: options.sourceFile,
        },
      });

      if (existingGraph) {
        if (options.overwrite) {
          await service.deleteGraph(existingGraph.id);
        } else {
          const counts = await resolveExistingCounts(service, existingGraph);
          return {
            graph: existingGraph,
            nodeCount: counts.nodeCount,
            edgeCount: counts.edgeCount,
            isNew: false,
          };
        }
      }

      const graph = await service.uploadDFGGraph(
        graphData.data,
        options.sourceFile,
        options.versionTag,
        meta
      );

      return {
        graph,
        nodeCount: countsFromData.nodeCount,
        edgeCount: countsFromData.edgeCount,
        isNew: true,
      };
    }

    case 'TEMPLATE': {
      const existingGraph = await service.client.graph.findFirst({
        where: {
          type: GraphType.TEMPLATE,
          sourceFile: options.sourceFile,
        },
      });

      if (existingGraph) {
        if (options.overwrite) {
          await service.deleteGraph(existingGraph.id);
        } else {
          const counts = await resolveExistingCounts(service, existingGraph);
          return {
            graph: existingGraph,
            nodeCount: counts.nodeCount,
            edgeCount: counts.edgeCount,
            isNew: false,
          };
        }
      }

      const graph = await service.uploadTemplateGraph(
        graphData.data,
        options.sourceFile,
        options.versionTag,
        meta
      );

      return {
        graph,
        nodeCount: countsFromData.nodeCount,
        edgeCount: countsFromData.edgeCount,
        isNew: true,
      };
    }

    default: {
      const exhaustive: never = graphData;
      throw new Error(
        `Unsupported graph type ${(exhaustive as Record<string, unknown>).type}`
      );
    }
  }
}

export async function uploadGraphs(
  graphDataList: Array<{ data: GraphData; options: GraphUploadOptions }>,
  service: DatabaseService = databaseService
): Promise<BulkUploadResult> {
  const results: DatabaseUploadResult[] = [];
  const errors: Array<{ file: string; error: string }> = [];

  for (const { data, options } of graphDataList) {
    try {
      const result = await uploadGraph(data, options, service);
      results.push(result);
    } catch (error) {
      errors.push({
        file: options.sourceFile,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return {
    successful: results.length,
    failed: errors.length,
    errors,
    results,
  };
}

export async function uploadGraphFromFile(
  filePath: string,
  graphType: GraphData['type'],
  options: Omit<GraphUploadOptions, 'sourceFile'>,
  service: DatabaseService = databaseService
): Promise<DatabaseUploadResult> {
  const absolutePath = path.resolve(filePath);
  const fileContents = await fs.readFile(absolutePath, 'utf8');
  const parsed = JSON.parse(fileContents);

  let graphData: GraphData;
  switch (graphType) {
    case 'AST':
      graphData = { type: 'AST', data: parsed as IASTGraph };
      break;
    case 'CPG':
      graphData = { type: 'CPG', data: parsed as CPGGraphData };
      break;
    case 'DFG':
      graphData = { type: 'DFG', data: parsed as IDFGGraph };
      break;
    case 'TEMPLATE':
      graphData = { type: 'TEMPLATE', data: parsed as TemplateFlattenedGraph };
      break;
    default:
      throw new Error(`Unsupported graph type ${graphType}`);
  }

  return uploadGraph(
    graphData,
    {
      ...options,
      sourceFile: absolutePath,
    },
    service
  );
}

export async function uploadGraphsFromDirectory(
  directoryPath: string,
  graphType: GraphData['type'],
  options: Omit<GraphUploadOptions, 'sourceFile'>,
  service: DatabaseService = databaseService
): Promise<BulkUploadResult> {
  const absolutePath = path.resolve(directoryPath);
  const entries = await fs.readdir(absolutePath, { withFileTypes: true });

  const files = entries
    .filter(
      (entry) => entry.isFile() && entry.name.toLowerCase().endsWith('.json')
    )
    .map((entry) => path.join(absolutePath, entry.name));

  const results: DatabaseUploadResult[] = [];
  const errors: Array<{ file: string; error: string }> = [];

  for (const file of files) {
    try {
      const result = await uploadGraphFromFile(
        file,
        graphType,
        options,
        service
      );
      results.push(result);
    } catch (error) {
      errors.push({
        file,
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return {
    successful: results.length,
    failed: errors.length,
    errors,
    results,
  };
}

export function validateGraphData(graphData: GraphData): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  switch (graphData.type) {
    case 'AST':
      if (!graphData.data.ast_result) {
        errors.push('AST data missing ast_result property');
      } else {
        if (!Array.isArray(graphData.data.ast_result.nodes)) {
          errors.push('AST nodes must be an array');
        }
        if (!Array.isArray(graphData.data.ast_result.edges_ast_pc)) {
          errors.push('AST edges_ast_pc must be an array');
        }
        if (!Array.isArray(graphData.data.ast_result.edges_ast_sb)) {
          errors.push('AST edges_ast_sb must be an array');
        }
        if (!Array.isArray(graphData.data.ast_result.edges_ast_guard)) {
          errors.push('AST edges_ast_guard must be an array');
        }
      }
      break;

    case 'CPG':
      if (!Array.isArray(graphData.data.vertices)) {
        errors.push('CPG vertices must be an array');
      }
      if (!Array.isArray(graphData.data.edges)) {
        errors.push('CPG edges must be an array');
      }
      break;

    case 'DFG':
      if (!Array.isArray(graphData.data.nodes)) {
        errors.push('DFG nodes must be an array');
      }
      if (!Array.isArray(graphData.data.edges)) {
        errors.push('DFG edges must be an array');
      }
      break;

    case 'TEMPLATE':
      if (!Array.isArray(graphData.data.nodes)) {
        errors.push('Template nodes must be an array');
      }
      if (!Array.isArray(graphData.data.edges)) {
        errors.push('Template edges must be an array');
      }
      break;

    default: {
      const exhaustive: never = graphData;
      errors.push(
        `Unknown graph type ${(exhaustive as Record<string, unknown>).type}`
      );
    }
  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
