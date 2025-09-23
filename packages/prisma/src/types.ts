import type { Graph } from '@prisma/client';
import { GraphType } from '@prisma/client';
// Import core types directly - no duplication
import type {
  CPGGraphData,
  IDFGGraph,
  TemplateFlattenedGraph,
  IASTResult,
} from '@ssat/core';

/**
 * Database upload result containing the created graph and metadata
 */
export interface DatabaseUploadResult {
  graph: Graph;
  nodeCount: number;
  edgeCount: number;
  isNew: boolean;
}

/**
 * Graph query filters
 */
export interface GraphFilters {
  type?: GraphType;
  sourceFile?: string;
  sourceLabel?: string;
  versionTag?: string;
  createdAfter?: Date;
  createdBefore?: Date;
}

/**
 * Graph upload options
 */
export interface GraphUploadOptions {
  sourceFile: string;
  sourceLabel?: string;
  versionTag?: string;
  overwrite?: boolean;
  meta?: Record<string, any>;
}

/**
 * Type-safe graph data union
 */
export type GraphData =
  | { type: 'AST'; data: IASTResult[] }
  | { type: 'CPG'; data: CPGGraphData }
  | { type: 'DFG'; data: IDFGGraph }
  | { type: 'TEMPLATE'; data: TemplateFlattenedGraph };

/**
 * Graph statistics
 */
export interface GraphStats {
  totalGraphs: number;
  graphsByType: Record<GraphType, number>;
  totalNodes: number;
  totalEdges: number;
  averageNodesPerGraph: number;
  averageEdgesPerGraph: number;
}

/**
 * Node query filters
 */
export interface NodeFilters {
  graphId?: string;
  label?: string;
  nodeType?: string;
  hasCode?: boolean;
  hasFeatures?: boolean;
}

/**
 * Edge query filters
 */
export interface EdgeFilters {
  graphId?: string;
  kind?: string;
  edgeType?: number;
  hasFeatures?: boolean;
}

/**
 * Graph search result with relevance score
 */
export interface GraphSearchResult {
  graph: Graph;
  score: number;
  matchedNodes: number;
  matchedEdges: number;
}

/**
 * Bulk upload result
 */
export interface BulkUploadResult {
  successful: number;
  failed: number;
  errors: Array<{ file: string; error: string }>;
  results: DatabaseUploadResult[];
}
