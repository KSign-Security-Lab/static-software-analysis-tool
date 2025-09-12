import { TemplateFlattenedGraph, TemplateNodes } from "../types/node";
import { TemplateNodeTypes } from "../types/template/BaseNode/BaseTypes";

export class PlanationTool {
  private blacklist: Set<TemplateNodeTypes>;
  private edges: { from: number; to: number }[] = [];
  private nodes: (TemplateNodes & { id: number })[] = [];

  constructor(blacklist: TemplateNodeTypes[] = []) {
    this.blacklist = new Set(blacklist);
  }

  /**
   * Given an array of root ASTNodes, returns one ASTFlattenedGraph per root,
   * where each graph has a flat list of nodes (with unique ids) and edges.
   */
  public flatten(astRoots: TemplateNodes[], removeBlackList = false): TemplateFlattenedGraph[] {
    const graphs: TemplateFlattenedGraph[] = [];

    for (const root of astRoots) {
      this.reset();
      this.traverse(root);

      // sort nodes by ascending id
      this.nodes.sort((a, b) => a.id - b.id);
      // sort edges by ascending sum of from+to
      this.edges.sort((e1, e2) => e1.from + e1.to - (e2.from + e2.to));

      // sanity-check that every edge references existing node ids
      this.validateEdges();

      graphs.push({
        edges: this.edges.slice(),
        nodes: this.nodes.slice(),
      });
    }

    if (removeBlackList) {
      // filter out blacklisted nodes
      for (const graph of graphs) {
        graph.nodes = graph.nodes.filter((node) => !this.blacklist.has(node.nodeType));
        graph.edges = graph.edges.filter((edge) => graph.nodes.some((n) => n.id === edge.from) && graph.nodes.some((n) => n.id === edge.to));
      }
    }

    return graphs;
  }

  /** Reset all internal state before processing a new root. */
  private reset(): void {
    this.edges = [];
    this.nodes = [];
  }

  /**
   * Walk the AST recursively, strip `children`, assign each node a unique `id`,
   * record the node and then traverse its children, recording an edge for each.
   * @returns the `id` assigned to this node
   */
  private traverse(node: TemplateNodes & { children?: TemplateNodes[] }): number {
    // clone node minus its children, attach id
    const { children, ...rest } = node;
    const clone: TemplateNodes & { id: number } = { ...(rest as TemplateNodes), id: node.id };
    this.nodes.push(clone);

    if (Array.isArray(children)) {
      for (const child of children) {
        const childId = this.traverse(child);
        this.edges.push({ from: clone.id, to: childId });
      }
    }

    return clone.id;
  }

  /**
   * Verify that each edge's `from` and `to` refer to an actual node ID in `this.nodes`.
   * Throws an error if any dangling reference is found.
   */
  private validateEdges(): void {
    const existingIds = new Set(this.nodes.map((n) => n.id));
    for (const { from, to } of this.edges) {
      if (!existingIds.has(from)) {
        throw new Error(`Edge refers to unknown source node id ${from.toString()}`);
      }
      if (!existingIds.has(to)) {
        throw new Error(`Edge refers to unknown target node id ${to.toString()}`);
      }
    }
  }
}
