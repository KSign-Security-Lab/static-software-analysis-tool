import { IASTResult } from "../types/ast";
import { IDFGEdge, IDFGGraph, IDFGNode } from "../types/dfg";
import { TemplateNodes, TemplateNodeTypes } from "../types/node";

class DFGSync {
  public syncPerFile(dfgGraphs: IDFGGraph[], astGraphs: IASTResult[], templates: TemplateNodes[]): IDFGGraph[] {
    const astNodeIds = astGraphs.map((ast) => ast.nodes.map((node) => node.orig_id));
    const syncedDfg: IDFGGraph[] = astNodeIds.map(() => ({ nodes: [], edges: [] }));
    const parentChildrenMap = this.buildDescendantIdMap(templates);
    const parentChildrenMapWithAstNodeIds = Object.keys(parentChildrenMap)
      .filter((parentKey) => astNodeIds.flat().includes(Number(parentKey)))
      .reduce<Record<string, number[]>>((acc, parentKey) => {
        acc[parentKey] = parentChildrenMap[parentKey];
        return acc;
      }, {});

    for (let i = 0; i < astNodeIds.length; i++) {
      const functionAstNodeIds = astNodeIds[i];
      const syncedNodes: IDFGNode[] = [];

      // Check if dfgGraphs[i] exists
      if (!dfgGraphs[i]) {
        console.warn(`DFG graph at index ${String(i)} is undefined, skipping...`);
        continue;
      }
      const dfgNodes = dfgGraphs[i].nodes;

      for (const astNode of astGraphs[i].nodes) {
        const astMatchingDfgNode = dfgNodes.find((n) => n.id === astNode.orig_id);
        if (astMatchingDfgNode && functionAstNodeIds.includes(astMatchingDfgNode.id)) {
          const astMatchingNode = astGraphs[i].nodes.find((n) => n.orig_id === astMatchingDfgNode.id);
          if (astMatchingNode) {
            astMatchingDfgNode.features.nodeType = astMatchingNode.node_type as TemplateNodeTypes;
            astMatchingDfgNode.sid = astMatchingNode.sid;
            syncedNodes.push(astMatchingDfgNode);
          }
        } else {
          syncedNodes.push({
            sid: astNode.sid,
            id: astNode.orig_id,
            features: {
              nodeType: astNode.node_type as TemplateNodeTypes,
              inDegreeDFG: 0,
              outDegreeDFG: 0,
              defCount: 0,
              useCount: 0,
              isBufferAccess: false,
              isSinkAssignment: false,
              isSinkCallUnbounded: false,
              isSinkCallBounded: false,
              callDestinationIndexed: false,
              callLengthLinkedToDestination: false,
              callSizeNonConstant: false,
              callDangerUnbounded: false,
            },
            debug: {
              info: "No matching DFG node found for AST node",
            },
          });
        }
      }

      const syncedEdges = this.redirectEdgesToParent(dfgGraphs[i].edges, parentChildrenMapWithAstNodeIds);

      syncedDfg[i].nodes.push(...syncedNodes.sort((a, b) => a.sid - b.sid));
      syncedDfg[i].edges.push(...syncedEdges.sort((a, b) => a.source - b.source));
    }

    return syncedDfg;
  }

  private redirectEdgesToParent(dfgEdges: IDFGEdge[], parentChildrenMapWithAstNodeIds: Record<string, number[]>): IDFGEdge[] {
    const redirectedEdges: IDFGEdge[] = [];
    for (const edge of dfgEdges) {
      const source = edge.source;
      const destination = edge.destination;
      const sourceParents = Object.keys(parentChildrenMapWithAstNodeIds).filter((parent) => parentChildrenMapWithAstNodeIds[parent].includes(source));
      const destinationParents = Object.keys(parentChildrenMapWithAstNodeIds).filter((parent) =>
        parentChildrenMapWithAstNodeIds[parent].includes(destination)
      );

      // Skip edges where nodes don't have parents in the mapping
      if (sourceParents.length === 0 || destinationParents.length === 0) {
        continue;
      }

      if (sourceParents.length !== 1) {
        throw new Error(
          `Source node ${source.toString()} has multiple parents: ${sourceParents.join(", ")}. Please check the ASTNodeIds. We should have a single parent for each node.`
        );
      }
      if (destinationParents.length !== 1) {
        throw new Error(`Destination node ${destination.toString()} has multiple parents: ${destinationParents.join(", ")}`);
      }
      redirectedEdges.push({ ...edge, source: Number(sourceParents[0]), destination: Number(destinationParents[0]) });
    }

    return redirectedEdges;
  }

  private buildDescendantIdMap(roots: TemplateNodes[]): Record<string, number[]> {
    // Build a map of direct children only (not all descendants)
    const byId = new Map<number, number[]>();

    function traverse(node: TemplateNodes) {
      const children = node.children ?? [];
      const childIds: number[] = [];

      for (const child of children) {
        childIds.push(child.id);
        traverse(child); // Recursively process children
      }

      byId.set(node.id, childIds);
    }

    for (const root of roots) {
      traverse(root);
    }

    // Map → plain object with string keys for safe Object.keys/Object.entries
    const result: Record<string, number[]> = {};
    for (const [id, list] of byId) result[id] = list;
    return result;
  }
}

export default DFGSync;
