import { IASTGraph } from "../types/ast";
import { CPGRoot } from "../types/cpg";
import { IDFGGraph } from "../types/dfg";
import { DFGEdgeBuilder } from "./DFGEdgeBuilder";
import { DFGNodeBuilder } from "./DFGNodeBuilder";
import DFGSync from "./DFGSync";

export class DFGBuilder {
  public build(cpg: CPGRoot, ast: IASTGraph): IDFGGraph {
    const edgeBuilder = new DFGEdgeBuilder(cpg);
    const { edges, degree, nodePartials } = edgeBuilder.buildEdges();

    const nodeBuilder = new DFGNodeBuilder(cpg);
    const nodes = nodeBuilder.buildNodes({ edges, degree, nodePartials });

    // Sort for stable output (optional)
    nodes.sort((a, b) => a.id - b.id);
    edges.sort((a, b) => a.source - b.source);

    const rawDFG: IDFGGraph = { nodes, edges };

    const syncedDfg = new DFGSync().sync(rawDFG, ast);

    return syncedDfg;
  }
}
