import { CPGRoot, EdgeGeneric, VertexGeneric } from "../types/cpg";
import { EdgeGraphSON, GraphSON, GraphSONValue } from "../types/cpg";
import { CallVertexProperties, ControlStructureVertexProperties } from "../types/cpg/vertex";
import { IDFGEdge, IDFGNodeFeature } from "../types/dfg";
import { FlowType, GuardType } from "../types/dfg";

export class DFGEdgeBuilder {
  private readonly cpg: CPGRoot;
  private readonly VbyId = new Map<number, VertexGeneric>();
  private readonly inE = new Map<number, EdgeGeneric[]>();
  private readonly outE = new Map<number, EdgeGeneric[]>();

  // Simple function-role table; extend/replace as needed.
  private readonly roleTable: Record<string, Record<number, ("VALUE" | "SIZE" | "INDEX")[]>> = {
    memcpy: { 1: ["VALUE"], 2: ["VALUE"], 3: ["SIZE"] },
    memmove: { 1: ["VALUE"], 2: ["VALUE"], 3: ["SIZE"] },
    memset: { 1: ["VALUE"], 3: ["SIZE"] },
    read: { 2: ["VALUE"], 3: ["SIZE"] }, // fd, buf, n
    recv: { 2: ["VALUE"], 3: ["SIZE"] },
    strcpy: { 1: ["VALUE"], 2: ["VALUE"] },
    strncpy: { 1: ["VALUE"], 2: ["VALUE"], 3: ["SIZE"] },
    strcat: { 1: ["VALUE"], 2: ["VALUE"] },
    snprintf: { 1: ["VALUE"], 2: ["SIZE"] },
    sprintf: { 1: ["VALUE"] },
    fgets: { 1: ["VALUE"], 2: ["SIZE"] }, // buf, size, stream
    getline: { 1: ["VALUE"], 2: ["SIZE"] },
  };

  // Unbounded / bounded call name matchers (lowercased).
  private readonly unboundedRx = /\b(strcpy|strcat|gets|sprintf|vsprintf)\b/;
  private readonly boundedRx = /\b(strncpy|snprintf|memcpy|memmove|fgets|read|recv|getline|memset)\b/;

  constructor(cpg: CPGRoot) {
    this.cpg = cpg;
    this.indexGraph();
  }

  public buildEdges(): {
    degree: Map<number, { inDeg: number; outDeg: number }>;
    edges: IDFGEdge[];
    nodePartials: Map<number, Partial<IDFGNodeFeature> & { debug?: Record<string, unknown> }>;
  } {
    const edges: IDFGEdge[] = [];
    const degree = new Map<number, { inDeg: number; outDeg: number }>();
    const nodePartials = new Map<number, Partial<IDFGNodeFeature> & { debug?: Record<string, unknown> }>();

    const dfgNodes = new Set<number>();
    for (const v of this.vertices()) {
      if (this.isDfgNode(v)) dfgNodes.add(this.vid(v));
    }

    // Pre-scan calls to collect node-level call flags (destination indexed, size linked, etc.)
    for (const v of this.vertices()) {
      if (v.label === "CALL") {
        const id = this.vid(v);
        const name = this.methodFullName(v).toLowerCase() || this.strArr((v.properties as CallVertexProperties).NAME)[0]?.toLowerCase() || "";
        const args = this.callArgs(v);
        const dst = args.find((a) => this.argIndex(a) === 1);
        const sizeArg = this.pickSizeArg(name, args);

        const flags: Partial<IDFGNodeFeature> = {
          isSinkCallUnbounded: this.unboundedRx.test(name),
          isSinkCallBounded: this.boundedRx.test(name),
          callDestinationIndexed: !!(dst && this.isIndexedExpr(dst)),
          callLengthLinkedToDestination: !!(dst && sizeArg && this.lenLinked(dst, sizeArg)),
          callSizeNonConstant: !!(sizeArg && sizeArg.label !== "LITERAL"),
          callDangerUnbounded: this.unboundedRx.test(name),
        };
        this.mergeNodePartial(nodePartials, id, flags, {
          callName: name,
          argCount: args.length,
        });
      }
    }

    // Build DFG edges from REACHING_DEF and AST only
    for (const e of this.edges()) {
      if (e.label !== "REACHING_DEF") continue;
      const src = this.VbyId.get(this.eno(e.outV));
      const dst = this.VbyId.get(this.eno(e.inV));
      if (!src || !dst) continue;
      const u = this.vid(src);
      const v = this.vid(dst);
      if (!dfgNodes.has(u) || !dfgNodes.has(v)) continue;

      // Classify flow type
      const flow = this.classifyFlowType(src, dst);

      // Compute guard features for the destination side
      const guard = this.guardForDestination(dst);

      // Compose edge
      const edge: IDFGEdge = {
        source: u,
        destination: v,
        features: {
          flow,
          guard: guard.guard,
          hasLowerGuard: guard.hasLowerGuard,
          hasUpperGuard: guard.hasUpperGuard,
          upperGuardNormalization: guard.upperGuardNormalization,
        },
        debug: {
          srcCode: this.code(src),
          dstCode: this.code(dst),
          call: this.methodFullName(this.enclosingCallOf(v)),
          guard: guard.debug,
        },
      };
      edges.push(edge);

      // Degrees
      const uD = degree.get(u) ?? { inDeg: 0, outDeg: 0 };
      const vD = degree.get(v) ?? { inDeg: 0, outDeg: 0 };
      uD.outDeg += 1;
      vD.inDeg += 1;
      degree.set(u, uD);
      degree.set(v, vD);

      // Node-level heuristics: buffer access / sink assignment
      // Mark the destination as buffer access/sink when array/pointer-style.
      if (this.isBufferAccess(dst)) {
        this.mergeNodePartial(nodePartials, v, { isBufferAccess: true }, { reason: "bufferAccess" });
      }
      if (this.isSinkAssignment(dst)) {
        this.mergeNodePartial(nodePartials, v, { isSinkAssignment: true }, { reason: "sinkAssign" });
      }
    }

    return { edges, degree, nodePartials };
  }

  // ---------- Helpers ----------

  private indexGraph(): void {
    const data = this.cpg.export["@value"];
    for (const v of data.vertices) {
      this.VbyId.set(v.id["@value"], v);
    }
    for (const e of data.edges) {
      const u = e.outV["@value"];
      const v = e.inV["@value"];
      if (!this.outE.has(u)) this.outE.set(u, []);
      if (!this.inE.has(v)) this.inE.set(v, []);
      this.outE.get(u)?.push(e);
      this.inE.get(v)?.push(e);
    }
  }

  private *vertices(): Iterable<VertexGeneric> {
    const data = this.cpg.export["@value"];
    for (const v of data.vertices) yield v;
  }

  private *edges(): Iterable<EdgeGeneric> {
    const data = this.cpg.export["@value"];
    for (const e of data.edges) yield e;
  }

  private vid(v: VertexGeneric): number {
    return v.id["@value"];
  }

  private eno(x: EdgeGraphSON<number>): number {
    return x["@value"];
  }

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

  private methodFullName(v?: VertexGeneric): string {
    if (!v || v.label !== "CALL") return "";
    const s = this.strArr((v.properties as CallVertexProperties).METHOD_FULL_NAME);
    return s[0] ?? "";
  }

  private argIndex(v: VertexGeneric): number | undefined {
    const anyProps = v.properties;
    if (!("ARGUMENT_INDEX" in anyProps)) return undefined;
    const idx = this.numVal(anyProps.ARGUMENT_INDEX as GraphSON<GraphSONValue>);
    return typeof idx === "number" ? idx : undefined;
  }

  private isDfgNode(v: VertexGeneric): boolean {
    switch (v.label) {
      case "CALL":
      case "FIELD_IDENTIFIER":
      case "IDENTIFIER":
      case "LITERAL":
      case "METHOD":
      case "METHOD_PARAMETER_IN":
      case "METHOD_PARAMETER_OUT":
      case "METHOD_RETURN":
        return true;
      default:
        return false;
    }
  }

  private enclosingCallOf(nodeId: number): VertexGeneric | undefined {
    const ins = this.inE.get(nodeId) ?? [];
    for (const e of ins) {
      if (e.label === "ARGUMENT") return this.VbyId.get(this.eno(e.outV));
    }
    return undefined;
  }

  private callArgs(callV: VertexGeneric): VertexGeneric[] {
    if (callV.label !== "CALL") return [];
    const outs = this.outE.get(this.vid(callV)) ?? [];
    return outs
      .filter((e) => e.label === "ARGUMENT")
      .map((e) => this.VbyId.get(this.eno(e.inV)))
      .filter((v): v is VertexGeneric => Boolean(v))
      .sort((a, b) => (this.argIndex(a) ?? 0) - (this.argIndex(b) ?? 0));
  }

  private baseName(methodFullName: string): string {
    const raw = methodFullName.split("::").pop() ?? methodFullName;
    return raw.split("(")[0];
  }

  private roleByCall(dst: VertexGeneric): FlowType | undefined {
    const call = this.enclosingCallOf(this.vid(dst));
    if (!call) return undefined;
    const name = this.baseName(this.methodFullName(call)).toLowerCase();
    const table = this.roleTable[name];

    const idx = this.argIndex(dst);
    if (idx == null) return undefined;
    const roles = table[idx] ?? [];
    if (roles.includes("SIZE")) return FlowType.SIZE;
    if (roles.includes("VALUE")) return FlowType.VALUE;
    if (roles.includes("INDEX")) return FlowType.INDEX;
    return undefined;
  }

  private isIndexedExpr(v: VertexGeneric): boolean {
    const c = this.code(v);
    // Simple detection: subscript or pointer arithmetic
    return /\[[^\]]+\]/.test(c) || /(\*|\+|-)\s*\w/.test(c);
  }

  private classifyFlowType(src: VertexGeneric, dst: VertexGeneric): FlowType {
    const viaCall = this.roleByCall(dst);
    if (viaCall) return viaCall;
    if (this.isIndexedExpr(dst)) return FlowType.INDEX;
    return FlowType.BASE; // Default “plumbing” if no stronger role was detected
  }

  private isBufferAccess(v: VertexGeneric): boolean {
    const c = this.code(v);
    return /\[[^\]]+\]/.test(c) || /\*(?:\s|\()*\w/.test(c);
  }

  private isSinkAssignment(v: VertexGeneric): boolean {
    // Heuristic: assignment-like code blobs land as CALL to <operator>.assignment or destination subscript usage
    const c = this.code(v);
    return /\[.*\]\s*=/.test(c) || c.includes("<operator>.assignment");
  }

  private controlsOf(nodeId: number): VertexGeneric[] {
    // CDG incoming: controller → node
    return (this.inE.get(nodeId) ?? [])
      .filter((e) => e.label === "CDG")
      .map((e) => this.VbyId.get(this.eno(e.outV)))
      .filter((v): v is VertexGeneric => Boolean(v));
  }

  private guardForDestination(dst: VertexGeneric): {
    debug: Record<string, unknown>;
    guard: GuardType;
    hasLowerGuard: boolean;
    hasUpperGuard: boolean;
    upperGuardNormalization: number;
  } {
    const ctrls = this.controlsOf(this.vid(dst));
    if (!ctrls.length) {
      return {
        guard: GuardType.NONE,
        hasLowerGuard: false,
        hasUpperGuard: false,
        upperGuardNormalization: 1,
        debug: {},
      };
    }

    // Pick nearest controller (first); you can extend to merge multiple
    const c = ctrls[0];
    let guard: GuardType = GuardType.NONE;
    let condCode = this.code(c);

    if (c.label === "CONTROL_STRUCTURE") {
      const t = (c.properties as ControlStructureVertexProperties).CONTROL_STRUCTURE_TYPE;
      const typeStr = this.strArr(t)[0]?.toUpperCase() ?? "";
      if (typeStr.includes("IF")) guard = GuardType.IF;
      else if (/(FOR|WHILE|DO)/.test(typeStr)) guard = GuardType.LOOP;

      // Try to fetch explicit CONDITION child code if present
      const outs = this.outE.get(this.vid(c)) ?? [];
      const condEdge = outs.find((e) => e.label === "CONDITION");
      if (condEdge) {
        const condV = this.VbyId.get(this.eno(condEdge.inV));
        if (condV) condCode = this.code(condV) || condCode;
      }
    }

    // Lightweight bound parsing
    const hasLowerGuard = /(>=|>)/.test(condCode);
    const hasUpperGuard = /(<=|<)/.test(condCode);
    const upperGuardNormalization = 1; // Keep 1 unless you implement literal normalization

    return {
      guard,
      hasLowerGuard,
      hasUpperGuard,
      upperGuardNormalization,
      debug: {
        controllerId: this.vid(c),
        controllerLabel: c.label,
        condition: condCode,
      },
    };
  }

  private lenLinked(dst: VertexGeneric, sizeArg: VertexGeneric): boolean {
    const d = this.code(dst);
    const s = this.code(sizeArg);
    if (!d || !s) return false;
    const base = d.replace(/\[.*\]/g, "");
    return (/sizeof\s*\(/.test(s) && s.includes(base)) || (/(ARRAY_SIZE|strlen)\s*\(/.test(s) && s.includes(base));
  }

  private pickSizeArg(callName: string, args: VertexGeneric[]): VertexGeneric | undefined {
    // crude, but works with our role table defaults
    const name = callName.toLowerCase();
    if (/(memcpy|memmove|strncpy|read|recv|memset)/.test(name)) {
      return args.find((a) => {
        const idx = this.argIndex(a);
        return idx === 3;
      });
    }
    if (/(snprintf|fgets|getline)/.test(name)) {
      return args.find((a) => this.argIndex(a) === 2);
    }
    return undefined;
  }

  private mergeNodePartial(
    map: Map<number, Partial<IDFGNodeFeature> & { debug?: Record<string, unknown> }>,
    nodeId: number,
    feat: Partial<IDFGNodeFeature>,
    debug?: Record<string, unknown>
  ): void {
    const prev = map.get(nodeId) ?? {};
    const next: Partial<IDFGNodeFeature> & { debug?: Record<string, unknown> } = { ...prev, ...feat };
    if (debug) {
      next.debug = { ...(prev.debug ?? {}), ...debug };
    }
    map.set(nodeId, next);
  }
}
