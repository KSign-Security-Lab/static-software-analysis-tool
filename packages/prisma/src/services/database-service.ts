import { createHash } from 'crypto';

import {
  PrismaClient,
  GraphType,
  ASTEdgeGroup,
  type Graph,
  Prisma,
} from '@prisma/client';
// Import core types directly - no duplication
import type {
  CPGGraphData,
  IDFGGraph,
  TemplateFlattenedGraph,
  IASTResult,
} from '@ssat/core';

export interface DatabaseServiceOptions {
  prisma?: PrismaClient;
}

export class DatabaseService {
  private readonly _prisma: PrismaClient;

  constructor(options: DatabaseServiceOptions = {}) {
    this._prisma = options.prisma ?? new PrismaClient();
  }

  get client(): PrismaClient {
    return this._prisma;
  }

  // Backwards-compatible accessor for legacy callers
  get prisma(): PrismaClient {
    return this._prisma;
  }

  async connect(): Promise<void> {
    await this._prisma.$connect();
  }

  async disconnect(): Promise<void> {
    await this._prisma.$disconnect();
  }

  async uploadASTGraph(
    astGraph: IASTResult[],
    sourceFile: string,
    versionTag?: string,
    meta: Record<string, unknown> = {},
    sourceLabel?: string
  ): Promise<Graph> {
    const contentHash = this.generateContentHash(astGraph);

    const existingGraph = await this._prisma.graph.findUnique({
      where: { contentHash },
    });
    if (existingGraph) {
      return existingGraph;
    }

    const astResults = astGraph;
    const allNodes = astResults.flatMap((r) => r.nodes);
    const allEdgesPc = astResults.flatMap((r) => r.edges_ast_pc);
    const allEdgesSb = astResults.flatMap((r) => r.edges_ast_sb);
    const allEdgesGuard = astResults.flatMap((r) => r.edges_ast_guard);

    const graph = await this._prisma.graph.create({
      data: {
        type: GraphType.AST,
        sourceFile,
        versionTag,
        contentHash,
        meta: {
          file: sourceFile,
          label: sourceLabel ?? sourceFile,
          sourceLabel: sourceLabel ?? sourceFile,
          nodeCount: allNodes.length,
          edgeCount:
            allEdgesPc.length + allEdgesSb.length + allEdgesGuard.length,
          ...meta,
        },
      },
    });

    await this._prisma.aSTNode.createMany({
      data: allNodes.map((node) => ({
        graphId: graph.id,
        sid: node.sid,
        origId: node.orig_id ? BigInt(node.orig_id) : null,
        nodeType: node.node_type,
        code: node.code,
        features: node.feat as unknown as Prisma.InputJsonValue,
        debug: null as unknown as Prisma.InputJsonValue,
      })),
      skipDuplicates: true,
    });

    await this._prisma.aSTEdge.createMany({
      data: [
        ...allEdgesPc.map(([src, dst, edgeType]) => ({
          graphId: graph.id,
          edgeGroup: ASTEdgeGroup.AST_PC,
          srcSid: src,
          dstSid: dst,
          kind: edgeType,
        })),
        ...allEdgesSb.map(([src, dst, edgeType]) => ({
          graphId: graph.id,
          edgeGroup: ASTEdgeGroup.AST_SB,
          srcSid: src,
          dstSid: dst,
          kind: edgeType,
        })),
        ...allEdgesGuard.map((guard) => ({
          graphId: graph.id,
          edgeGroup: ASTEdgeGroup.AST_GUARD,
          srcSid: guard.src,
          dstSid: guard.dst,
          kind: guard.edge_type,
          guardKind: guard.guard_kind,
          guardBranch: guard.guard_branch,
        })),
      ],
      skipDuplicates: true,
    });

    return graph;
  }

  async uploadCPGGraph(
    cpgData: CPGGraphData,
    sourceFile: string,
    versionTag?: string,
    _meta: Record<string, unknown> = {}
  ): Promise<Graph> {
    // CPG graphs are not supported in the current schema
    // This method is kept for API compatibility but does nothing
    throw new Error('CPG graph upload is not supported in the current schema');
  }

  async uploadDFGGraph(
    dfgGraph: IDFGGraph,
    sourceFile: string,
    versionTag?: string,
    meta: Record<string, unknown> = {}
  ): Promise<Graph> {
    const contentHash = this.generateContentHash(dfgGraph);

    const existingGraph = await this._prisma.graph.findUnique({
      where: { contentHash },
    });
    if (existingGraph) {
      return existingGraph;
    }

    const graph = await this._prisma.graph.create({
      data: {
        type: GraphType.DFG,
        sourceFile,
        versionTag,
        contentHash,
        meta: {
          nodeCount: dfgGraph.nodes.length,
          edgeCount: dfgGraph.edges.length,
          ...meta,
        },
      },
    });

    await this._prisma.dFGNode.createMany({
      data: dfgGraph.nodes.map((node) => ({
        graphId: graph.id,
        origId: node.id,
        templateNodeType: node.features.nodeType,
        inDegreeDFG: node.features.inDegreeDFG,
        outDegreeDFG: node.features.outDegreeDFG,
        defCount: node.features.defCount,
        useCount: node.features.useCount,
        isBufferAccess: node.features.isBufferAccess,
        isSinkAssignment: node.features.isSinkAssignment,
        isSinkCallUnbounded: node.features.isSinkCallUnbounded,
        isSinkCallBounded: node.features.isSinkCallBounded,
        callDestinationIndexed: node.features.callDestinationIndexed,
        callLengthLinkedToDestination:
          node.features.callLengthLinkedToDestination,
        callSizeNonConstant: node.features.callSizeNonConstant,
        callDangerUnbounded: node.features.callDangerUnbounded,
        debug: (node.debug ?? null) as unknown as Prisma.InputJsonValue,
      })),
      skipDuplicates: true,
    });

    await this._prisma.dFGEdge.createMany({
      data: dfgGraph.edges.map((edge) => ({
        graphId: graph.id,
        srcOrigId: edge.source,
        dstOrigId: edge.destination,
        flow: edge.features.flow,
        guard: edge.features.guard,
        hasLowerGuard: edge.features.hasLowerGuard,
        hasUpperGuard: edge.features.hasUpperGuard,
        upperGuardNormalization: edge.features.upperGuardNormalization,
        debug: (edge.debug ?? null) as unknown as Prisma.InputJsonValue,
      })),
      skipDuplicates: true,
    });

    return graph;
  }

  async uploadTemplateGraph(
    templateGraph: TemplateFlattenedGraph,
    sourceFile: string,
    versionTag?: string,
    _meta: Record<string, unknown> = {}
  ): Promise<Graph> {
    // Template graphs are not supported in the current schema
    // This method is kept for API compatibility but does nothing
    throw new Error(
      'Template graph upload is not supported in the current schema'
    );
  }

  async getGraphById(graphId: string): Promise<Graph | null> {
    return this._prisma.graph.findUnique({
      where: { id: graphId },
      include: {
        astNodes: true,
        astEdges: true,
        dfgNodes: true,
        dfgEdges: true,
      },
    });
  }

  async getGraphsByTypeAndFile(
    type: GraphType,
    sourceFile: string
  ): Promise<Graph[]> {
    return this._prisma.graph.findMany({
      where: {
        type,
        sourceFile,
      },
      include: {
        astNodes: true,
        astEdges: true,
        dfgNodes: true,
        dfgEdges: true,
      },
    });
  }

  async deleteGraph(graphId: string): Promise<Graph> {
    return this._prisma.graph.delete({
      where: { id: graphId },
    });
  }

  private generateContentHash(data: unknown): string {
    const payload = JSON.stringify(data);
    return createHash('sha256').update(payload).digest('hex');
  }

  private extractLineNumber(properties: unknown): number | null {
    if (
      properties &&
      typeof properties === 'object' &&
      'LINE_NUMBER' in properties
    ) {
      const lineNumber = (properties as Record<string, unknown>).LINE_NUMBER;
      if (
        lineNumber &&
        typeof lineNumber === 'object' &&
        '@value' in lineNumber
      ) {
        const value = (lineNumber as Record<string, unknown>)['@value'];
        return Array.isArray(value) ? (value[0] as number) : (value as number);
      }
    }
    return null;
  }

  private extractColumnNumber(properties: unknown): number | null {
    if (
      properties &&
      typeof properties === 'object' &&
      'COLUMN_NUMBER' in properties
    ) {
      const columnNumber = (properties as Record<string, unknown>)
        .COLUMN_NUMBER;
      if (
        columnNumber &&
        typeof columnNumber === 'object' &&
        '@value' in columnNumber
      ) {
        const value = (columnNumber as Record<string, unknown>)['@value'];
        return Array.isArray(value) ? (value[0] as number) : (value as number);
      }
    }
    return null;
  }
}

export const databaseService = new DatabaseService();
