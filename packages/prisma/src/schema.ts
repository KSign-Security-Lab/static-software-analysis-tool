export { GraphType } from '@prisma/client';
export type { Graph, ASTNode, ASTEdge, DFGNode, DFGEdge } from '@prisma/client';

// Re-export core types directly - no duplication
export type {
  IASTGraph,
  CPGGraphData,
  IDFGGraph,
  TemplateFlattenedGraph,
} from '@ssat/core';
