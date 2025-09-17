import { IASTResult } from "../types/ast";
import { CPGRoot } from "../types/cpg";
import { IDFGGraph } from "../types/dfg";
import { TemplateNodes } from "../types/node";
import { DFGEdgeBuilder } from "./DFGEdgeBuilder";
import { DFGNodeBuilder } from "./DFGNodeBuilder";
import DFGSync from "./DFGSync";

export class DFGBuilder {
  public build(cpg: CPGRoot, asts: IASTResult[], templates: TemplateNodes[]): IDFGGraph[] {
    const edgeBuilder = new DFGEdgeBuilder(cpg);
    const { edges, degree, nodePartials } = edgeBuilder.buildEdges();

    const nodeBuilder = new DFGNodeBuilder(cpg);
    const nodes = nodeBuilder.buildNodes({ edges, degree, nodePartials });

    // Sort for stable output (optional)
    nodes.sort((a, b) => a.id - b.id);
    edges.sort((a, b) => a.source - b.source);

    const rawDFG: IDFGGraph[] = [{ nodes, edges }];

    const syncedDfg = new DFGSync().sync(rawDFG, asts, templates);

    return syncedDfg;
  }
}
