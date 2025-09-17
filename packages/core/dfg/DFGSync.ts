import { IASTResult } from "../types/ast";
import { IDFGGraph } from "../types/dfg";
import { TemplateNodes, TemplateNodeTypes } from "../types/node";

class DFGSync {
  public sync(dfgGraphs: IDFGGraph[], astGraphs: IASTResult[], templates: TemplateNodes[]): IDFGGraph[] {
    astGraphs.forEach((ast) => {
      this.validateAST(ast);
    });
    const syncedDfg: IDFGGraph[] = astGraphs.map(() => ({ nodes: [], edges: [] }));
    const parentChildrenMap = this.buildDescendantIdMap(templates);
    const allNodeIdsInAst = astGraphs.flatMap((ast) => ast.nodes.flatMap((n) => n.orig_id));
    for (const key of Object.keys(parentChildrenMap)) {
      if (!allNodeIdsInAst.includes(Number(key))) {
        Reflect.deleteProperty(parentChildrenMap, key);
      }
    }

    for (let i = 0; i < Math.min(dfgGraphs.length, astGraphs.length); i++) {
      const dfg = dfgGraphs[i];
      const ast = astGraphs[i];
      syncedDfg[i].nodes = dfg.nodes.filter((item) => new Set(ast.nodes.map((n) => n.orig_id)).has(item.id));
      syncedDfg[i].nodes.forEach((node) => {
        node.id = ast.nodes.find((astNode) => astNode.orig_id === node.id)?.sid ?? node.id;
        node.features.nodeType = ast.nodes.find((astNode) => astNode.orig_id === node.id)?.node_type as TemplateNodeTypes;
      });
      syncedDfg[i].nodes.sort((a, b) => a.id - b.id);
      for (const edge of dfg.edges) {
        for (const [key, value] of Object.entries(parentChildrenMap)) {
          const newEdge = { ...edge };
          if (value.includes(edge.source)) {
            newEdge.source = Number(key);
          }

          if (value.includes(edge.destination)) {
            newEdge.destination = Number(key);
          }

          if (newEdge.source === newEdge.destination) {
            continue;
          }
          if (value.includes(newEdge.source) && value.includes(newEdge.destination)) {
            syncedDfg[i].edges.push(newEdge);
          }
        }
      }
    }

    return syncedDfg;
  }

  private validateAST(ast: IASTResult): void {
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast) {
      throw new Error("AST is undefined");
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast.nodes) {
      throw new Error("AST has no nodes");
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast.edges_ast_pc) {
      throw new Error("AST has no edges");
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast.edges_ast_sb) {
      throw new Error("AST has no edges");
    }
    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
    if (!ast.edges_ast_guard) {
      throw new Error("AST has no edges");
    }
  }

  private buildDescendantIdMap(roots: TemplateNodes[]): Record<string, number[]> {
    // Post-order traversal without recursion
    const post: TemplateNodes[] = [];
    const stack: { idx: number; node: TemplateNodes }[] = [];

    for (const root of roots) {
      stack.push({ node: root, idx: 0 });
      while (stack.length) {
        const top = stack[stack.length - 1];
        const children = top.node.children ?? [];
        if (top.idx < children.length) {
          const child = children[top.idx];
          top.idx += 1;
          stack.push({ node: child, idx: 0 });
        } else {
          post.push(top.node);
          stack.pop();
        }
      }
    }

    // Accumulate descendant ids bottom-up
    const byId = new Map<number, number[]>();
    for (const node of post) {
      const children = node.children ?? [];
      const desc: number[] = [];
      for (const child of children) {
        const childDesc = byId.get(child.id);
        desc.push(child.id, ...(childDesc ?? []));
      }
      byId.set(node.id, desc);
    }

    // Map → plain object with string keys for safe Object.keys/Object.entries
    const result: Record<string, number[]> = {};
    for (const [id, list] of byId) result[id] = list;
    return result;
  }
}

export default DFGSync;
