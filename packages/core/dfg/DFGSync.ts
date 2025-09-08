import { IDFGGraph } from "../types/dfg";
import { TemplateFlattenedGraph } from "../types/node";

class DFGSync {
  private readonly dfg: IDFGGraph;
  private readonly ast: TemplateFlattenedGraph;

  constructor(dfg: IDFGGraph, ast: TemplateFlattenedGraph) {
    this.dfg = dfg;
    this.ast = ast;
  }

  public sync(): IDFGGraph {
    const syncedDfg: IDFGGraph = { nodes: [], edges: [] };
    const astUniqueNodeIds = new Set(this.ast.nodes.map((n) => n.id));
    syncedDfg.nodes = this.dfg.nodes.filter((n) => astUniqueNodeIds.has(n.id));
    for (const node of syncedDfg.nodes) {
      const astNode = this.ast.nodes.find((n) => n.id === node.id);
      // Force type check without type assertion
      // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
      if (astNode && astNode.nodeType) {
        node.features.nodeType = astNode.nodeType;
      }
    }
    // Use && to ensure both source and destination are present in the AST, not just one.
    // Using || would allow edges to be present in the DFG but not in the AST, which is not what we want.
    syncedDfg.edges = this.dfg.edges.filter((e) => astUniqueNodeIds.has(e.source) && astUniqueNodeIds.has(e.destination));

    return syncedDfg;
  }
}

export default DFGSync;
