import { TemplateNodeTypes } from "../types";
import { IASTGraph } from "../types/ast";
import { IDFGGraph } from "../types/dfg";

class DFGSync {
  private validateAST(ast: IASTGraph): void {
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast) {
      throw new Error("AST is undefined");
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast.ast_result) {
      throw new Error("AST has no ast_result");
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast.ast_result.nodes) {
      throw new Error("AST has no nodes");
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast.ast_result.edges_ast_pc) {
      throw new Error("AST has no edges");
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast.ast_result.edges_ast_sb) {
      throw new Error("AST has no edges");
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast.ast_result.edges_ast_guard) {
      throw new Error("AST has no edges");
    }
    if (!ast.ast_result.nodes.length) {
      throw new Error("AST has no nodes");
    }
    if (!ast.ast_result.edges_ast_pc.length) {
      throw new Error("AST has no edges");
    }
    if (!ast.ast_result.edges_ast_sb.length) {
      throw new Error("AST has no edges");
    }
    if (!ast.ast_result.edges_ast_guard.length) {
      throw new Error("AST has no edges");
    }
  }

  public sync(dfg: IDFGGraph, ast: IASTGraph): IDFGGraph {
    this.validateAST(ast);
    const syncedDfg: IDFGGraph = { nodes: [], edges: [] };
    const astUniqueNodeIds = new Set(ast.ast_result.nodes.map((n) => n.orig_id));
    syncedDfg.nodes = dfg.nodes.filter((n) => astUniqueNodeIds.has(n.id));
    for (const node of syncedDfg.nodes) {
      const astNode = ast.ast_result.nodes.find((n) => n.orig_id === node.id);
      // If node does not exist then throw error
      if (!astNode) {
        throw new Error(`Node ${node.id.toString()} does not exist in the AST`);
      }

      // Force type check without type assertion

      if (astNode.node_type) {
        node.features.nodeType = astNode.node_type as TemplateNodeTypes;
      }
    }
    // Use && to ensure both source and destination are present in the AST, not just one.
    // Using || would allow edges to be present in the DFG but not in the AST, which is not what we want.
    syncedDfg.edges = dfg.edges.filter((e) => astUniqueNodeIds.has(e.source) && astUniqueNodeIds.has(e.destination));

    return syncedDfg;
  }
}

export default DFGSync;
