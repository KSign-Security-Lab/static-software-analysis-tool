import { CPGRoot } from "@/types/cpg";
import { IDFGGraph } from "@/types/dfg";

import { DFGEdgeBuilder } from "./DFGEdgeBuilder";
import { DFGNodeBuilder } from "./DFGNodeBuilder";

export class DFGBuilder {
  private readonly cpg: CPGRoot;

  constructor(cpg: CPGRoot) {
    this.cpg = cpg;
  }

  public build(): IDFGGraph {
    const edgeBuilder = new DFGEdgeBuilder(this.cpg);
    const { edges, degree, nodePartials } = edgeBuilder.buildEdges();

    const nodeBuilder = new DFGNodeBuilder(this.cpg);
    const nodes = nodeBuilder.buildNodes({ edges, degree, nodePartials });

    // Sort for stable output (optional)
    nodes.sort((a, b) => a.id - b.id);

    return { nodes, edges };
  }
}
