export {
  DatabaseService,
  databaseService,
  type DatabaseServiceOptions,
} from './services/database-service';

export type {
  GraphData,
  GraphUploadOptions,
  DatabaseUploadResult,
  BulkUploadResult,
  GraphFilters,
  GraphStats,
  GraphSearchResult,
  NodeFilters,
  EdgeFilters,
} from './types';

export {
  uploadGraph,
  uploadGraphs,
  uploadGraphFromFile,
  uploadGraphsFromDirectory,
  validateGraphData,
} from './upload-utils';

export {
  getDatabaseConfig,
  validateDatabaseConfig,
  DEFAULT_DATABASE_CONFIG,
} from './config';

export { GraphType } from '@prisma/client';
export type { Graph, ASTNode, ASTEdge, DFGNode, DFGEdge } from '@prisma/client';

// Re-export core types directly - no duplication
export type {
  IASTResult,
  CPGGraphData,
  IDFGGraph,
  TemplateFlattenedGraph,
} from '@ssat/core';
