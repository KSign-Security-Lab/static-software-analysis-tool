import { CPGRoot, VertexGeneric } from "../types/cpg";
import { GraphSON, GraphSONValue } from "../types/cpg";
import { IDFGEdge, IDFGNode, IDFGNodeFeature } from "../types/dfg";
import { FlowType } from "../types/dfg";

export class DFGNodeBuilder {
  private readonly cpg: CPGRoot;
  private readonly VbyId = new Map<number, VertexGeneric>();

  constructor(cpg: CPGRoot) {
    this.cpg = cpg;
    const data = this.cpg.export["@value"];
    for (const v of data.vertices) this.VbyId.set(v.id["@value"], v);
  }

  public buildNodes(input: {
    degree: Map<number, { inDeg: number; outDeg: number }>;
    edges: IDFGEdge[];
    nodePartials: Map<number, Partial<IDFGNodeFeature> & { debug?: Record<string, unknown> }>;
  }): IDFGNode[] {
    const { edges, degree, nodePartials } = input;

    // Precompute per-node useCount that EXCLUDES BASE incoming edges
    const nonBaseIncoming = new Map<number, number>();
    for (const e of edges) {
      if (e.features.flow === FlowType.BASE) continue;
      nonBaseIncoming.set(e.destination, (nonBaseIncoming.get(e.destination) ?? 0) + 1);
    }

    // Gather all DFG node IDs that appear in edges (src or dst)
    const nodeIds = new Set<number>();
    for (const e of edges) {
      nodeIds.add(e.source);
      nodeIds.add(e.destination);
    }

    const nodes: IDFGNode[] = [];
    for (const id of nodeIds) {
      const v = this.VbyId.get(id);
      if (!v) continue;

      const deg = degree.get(id) ?? { inDeg: 0, outDeg: 0 };
      const partial = nodePartials.get(id) ?? {};

      const features: IDFGNodeFeature = {
        nodeType: v.label as unknown as IDFGNodeFeature["nodeType"],
        inDegreeDFG: deg.inDeg,
        outDegreeDFG: deg.outDeg,
        defCount: deg.outDeg, // definition → outgoing REACHING_DEF edges
        useCount: nonBaseIncoming.get(id) ?? 0, // exclude BASE from uses
        isBufferAccess: !!partial.isBufferAccess,
        isSinkAssignment: !!partial.isSinkAssignment,
        isSinkCallUnbounded: !!partial.isSinkCallUnbounded,
        isSinkCallBounded: !!partial.isSinkCallBounded,
        callDestinationIndexed: !!partial.callDestinationIndexed,
        callLengthLinkedToDestination: !!partial.callLengthLinkedToDestination,
        callSizeNonConstant: !!partial.callSizeNonConstant,
        callDangerUnbounded: !!partial.callDangerUnbounded,
      };

      const debug: Record<string, unknown> = {
        ...(partial.debug ?? {}),
        label: v.label,
        code: this.code(v),
        type: this.typeFullName(v),
        file: this.fileName(v),
        line: this.lineNumber(v),
      };

      nodes.push({ sid: -999, id, features, debug });
    }

    return nodes;
  }

  // ---------- helpers ----------
  private strArr(gx?: GraphSON<string[]>): string[] {
    return gx?.["@value"]?.["@value"] ?? [];
  }
  private numVal(gx?: GraphSON<GraphSONValue>): number | undefined {
    const raw = gx?.["@value"]?.["@value"];
    return typeof raw === "number" ? raw : Number.isFinite(Number(raw)) ? Number(raw) : undefined;
  }
  private code(v: VertexGeneric): string {
    const anyProps = v.properties;
    if (!("CODE" in anyProps)) return "";
    const s = this.strArr(anyProps.CODE as GraphSON<string[]>);
    return s[0] ?? "";
  }
  private typeFullName(v: VertexGeneric): string {
    const anyProps = v.properties;
    if (!("TYPE_FULL_NAME" in anyProps)) return "";
    const s = this.strArr(anyProps.TYPE_FULL_NAME as GraphSON<string[]>);
    return s[0] ?? "";
  }
  private fileName(v: VertexGeneric): string {
    // METHOD or NAMESPACE_BLOCK often carry FILENAME; fall back to METHOD if present
    const anyProps = v.properties;
    if (!("FILENAME" in anyProps)) return "";
    const p = this.strArr(anyProps.FILENAME);
    return p[0] ?? "";
  }
  private lineNumber(v: VertexGeneric): number | undefined {
    const anyProps = v.properties;
    if (!("LINE_NUMBER" in anyProps)) return undefined;
    return this.numVal(anyProps.LINE_NUMBER);
  }
}
