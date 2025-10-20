import type { IASTNode, IASTResult } from "../types/ast";
import type { TemplateNodes } from "../types/template";

import { CPGRoot, VertexGeneric } from "../types/cpg";
import { FlowType, GuardType, IDFGEdge, IDFGEdgeFeature, IDFGGraph, IDFGNode, IDFGNodeFeature } from "../types/dfg";
import { TemplateNodeTypes } from "../types/template/BaseNode/BaseTypes";

const EMPTY_NODE_FEATURE: IDFGNodeFeature = {
  nodeType: "UNKNOWN" as TemplateNodeTypes,
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
};

export class DFGBuilder {
  constructor(
    private cpg: CPGRoot,
    private ast: IASTResult,
    private template: TemplateNodes
  ) {}

  public buildDFGFromCPG(): IDFGGraph {
    const nodes = this.buildNodes();
    const edges = this.buildEdges();

    const childToAncestor = this.createEdgeRedirectionMap(this.ast.nodes, this.template);
    const syncedDfgNodes = this.syncDfgNodesWithAstNodes(nodes, this.ast.nodes, childToAncestor);
    const redirectedEdges = this.redirectEdgesByRedirectionMap(edges, childToAncestor);

    this.updateNodeDegrees(syncedDfgNodes, redirectedEdges);
    const uniqueEdges = this.filterIdenticalEdges(redirectedEdges);
    return { nodes: syncedDfgNodes, edges: uniqueEdges };
  }

  private buildNodes(): IDFGNode[] {
    // de-dup nodes by CPG vertex id
    const byId = new Map<number, IDFGNode>();

    const refEdges = this.cpg.export["@value"].edges.filter((e) => e.label === "REF");
    const allowedDecl = new Set(["LOCAL", "MEMBER", "METHOD_PARAMETER_IN", "METHOD_PARAMETER_OUT", "PARAMETER", "PARAMETER_IN", "PARAMETER_OUT"]);

    const getOrCreate = (v: VertexGeneric): IDFGNode => {
      const id = v.id["@value"];
      const exist = byId.get(id);
      if (exist) return exist;

      const node: IDFGNode = {
        sid: -999, // will be filled from AST if available
        id,
        features: { ...EMPTY_NODE_FEATURE }, // we'll merge real features later
        debug: {
          label: this.getLabel(v),
          name: this.getName(v) ?? this.getCode(v) ?? "<unnamed>",
          line: this.getLineNumber(v),
        },
      };
      byId.set(id, node);
      return node;
    };

    // collect candidate vertices and count defs/uses
    for (const ref of refEdges) {
      const use = this.getNodeById(ref.outV["@value"]);
      const def = this.getNodeById(ref.inV["@value"]);
      if (!use || !def) continue;
      if (this.getLabel(use) !== "IDENTIFIER") continue;
      if (!allowedDecl.has(this.getLabel(def))) continue;

      const useNode = getOrCreate(use);
      const defNode = getOrCreate(def);

      useNode.features.useCount += 1;
      defNode.features.defCount += 1;
    }

    // compute full feature set per node (preserve counted def/use)
    for (const node of byId.values()) {
      const countedDef = node.features.defCount;
      const countedUse = node.features.useCount;
      const base = this.computeNodeFeature(node.id);
      node.features = {
        ...base,
        defCount: countedDef,
        useCount: countedUse,
        inDegreeDFG: 0,
        outDegreeDFG: 0,
      };
    }

    return [...byId.values()];
  }

  private buildEdges(): IDFGEdge[] {
    const edges: IDFGEdge[] = [];

    const refEdges = this.cpg.export["@value"].edges.filter((e) => e.label === "REF");
    const allowedDecl = new Set(["LOCAL", "MEMBER", "METHOD_PARAMETER_IN", "METHOD_PARAMETER_OUT", "PARAMETER", "PARAMETER_IN", "PARAMETER_OUT"]);

    for (const ref of refEdges) {
      const use = this.getNodeById(ref.outV["@value"]);
      const def = this.getNodeById(ref.inV["@value"]);
      if (!use || !def) continue;
      if (this.getLabel(use) !== "IDENTIFIER") continue;
      if (!allowedDecl.has(this.getLabel(def))) continue;

      const feat = this.computeEdgeFeature(def, use);
      const edge: IDFGEdge = {
        source: def.id["@value"],
        destination: use.id["@value"],
        features: feat,
        debug: {
          var: this.getName(use) ?? this.getCode(use),
          srcLine: this.getLineNumber(def),
          dstLine: this.getLineNumber(use),
        },
      };
      edges.push(edge);
    }

    return edges;
  }

  private syncDfgNodesWithAstNodes(dfgNodes: IDFGNode[], astNodes: IASTNode[], childToAncestor: Record<number, number>): IDFGNode[] {
    const syncedNodes: IDFGNode[] = [];
    const parentToChildren = new Map<number, number[]>();
    for (const [child, parent] of Object.entries(childToAncestor)) {
      if (!parentToChildren.has(parent)) {
        parentToChildren.set(parent, []);
      }
      parentToChildren.get(parent)?.push(Number(child));
    }

    for (const astNode of astNodes) {
      let matchingDfgNode = dfgNodes.find((n) => astNode.orig_id === n.id);
      if (matchingDfgNode) {
        matchingDfgNode.sid = astNode.sid;
      } else {
        const node = this.getNodeById(astNode.orig_id);
        if (!node) {
          matchingDfgNode = {
            sid: astNode.sid,
            id: astNode.orig_id,
            features: { ...EMPTY_NODE_FEATURE },
            debug: { label: "<node>", name: "<unnamed>", line: null, info: "No matching DFG node found for AST node" },
          };
        } else {
          matchingDfgNode = {
            sid: astNode.sid,
            id: astNode.orig_id,
            features: { ...EMPTY_NODE_FEATURE },
            debug: {
              label: this.getLabel(node),
              name: this.getName(node),
              line: this.getLineNumber(node),
              info: "No matching DFG node found for AST node",
            },
          };
        }
      }

      for (const parent of parentToChildren.get(matchingDfgNode.id) ?? []) {
        const parentDfgNode = dfgNodes.find((n) => n.id === parent);
        if (!parentDfgNode) continue;
        for (const child of parentToChildren.get(parent) ?? []) {
          if (child === matchingDfgNode.id) continue;
          const childDfgNode = dfgNodes.find((n) => n.id === child);
          if (!childDfgNode) continue;
          parentDfgNode.features.outDegreeDFG += childDfgNode.features.outDegreeDFG;
          parentDfgNode.features.inDegreeDFG += childDfgNode.features.inDegreeDFG;
          parentDfgNode.features.defCount += childDfgNode.features.defCount;
          parentDfgNode.features.useCount += childDfgNode.features.useCount;
          parentDfgNode.features.isBufferAccess = parentDfgNode.features.isBufferAccess || childDfgNode.features.isBufferAccess;
          parentDfgNode.features.isSinkAssignment = parentDfgNode.features.isSinkAssignment || childDfgNode.features.isSinkAssignment;
          parentDfgNode.features.isSinkCallUnbounded = parentDfgNode.features.isSinkCallUnbounded || childDfgNode.features.isSinkCallUnbounded;
          parentDfgNode.features.isSinkCallBounded = parentDfgNode.features.isSinkCallBounded || childDfgNode.features.isSinkCallBounded;
          parentDfgNode.features.callDestinationIndexed =
            parentDfgNode.features.callDestinationIndexed || childDfgNode.features.callDestinationIndexed;
          parentDfgNode.features.callLengthLinkedToDestination =
            parentDfgNode.features.callLengthLinkedToDestination || childDfgNode.features.callLengthLinkedToDestination;
          parentDfgNode.features.callSizeNonConstant = parentDfgNode.features.callSizeNonConstant || childDfgNode.features.callSizeNonConstant;
          parentDfgNode.features.callDangerUnbounded = parentDfgNode.features.callDangerUnbounded || childDfgNode.features.callDangerUnbounded;
        }
      }
      syncedNodes.push(matchingDfgNode);
    }
    return syncedNodes;
  }

  private createEdgeRedirectionMap(astNodes: IASTNode[], template: TemplateNodes): Record<number, number> {
    const selected = new Set(astNodes.map((n) => n.orig_id));
    const childToAncestor: Record<number, number> = {};

    const dfs = (node: TemplateNodes, currentAncestor: number | null): void => {
      const isSelected = selected.has(node.id);
      const nextAncestor = isSelected ? node.id : currentAncestor;

      // If node is NOT selected but we have a selected ancestor, map this node to that ancestor
      if (!isSelected && nextAncestor !== null) {
        childToAncestor[node.id] = nextAncestor;
      }

      const children = node.children ?? [];
      for (const ch of children) dfs(ch, nextAncestor);
    };

    dfs(template, null);
    return childToAncestor;
  }

  private redirectEdgesByRedirectionMap(dfgEdges: IDFGEdge[], childToAncestor: Record<number, number>): IDFGEdge[] {
    const out: IDFGEdge[] = [];
    for (const e of dfgEdges) {
      const newSource = childToAncestor[e.source] ?? e.source;
      const newDestination = childToAncestor[e.destination] ?? e.destination;

      if (newSource === newDestination) continue;

      out.push({
        source: newSource,
        destination: newDestination,
        features: e.features,
        debug: e.debug,
      });
    }
    return out;
  }

  private filterIdenticalEdges(edges: IDFGEdge[]): IDFGEdge[] {
    const uniqueObjectsSet = new Set(edges.map((obj) => JSON.stringify(obj)));
    const uniqueArray = Array.from(uniqueObjectsSet).map((str) => JSON.parse(str) as IDFGEdge);
    return uniqueArray;
  }

  private computeNodeFeature(cpgId: number): IDFGNodeFeature {
    const f = { ...EMPTY_NODE_FEATURE };
    const v = this.getNodeById(cpgId);
    if (!v) return f;

    f.nodeType = this.inferTemplateType(v);

    const parents = this.getAstParents(cpgId)
      .map((pid) => this.getNodeById(pid))
      .filter(Boolean) as VertexGeneric[];

    const isArrayIndexContext = parents.some((p) => this.getLabel(p) === "CALL" && /\[.+\]/.test(this.getCode(p) ?? ""));
    const isPointerDeref = parents.some((p) => (this.getCode(p)?.includes("*(") ?? false) || (this.getCode(p)?.includes("->") ?? false));
    f.isBufferAccess = isArrayIndexContext || isPointerDeref;

    const isAssignment = parents.some((p) => (this.getCode(p) ?? "").includes("="));
    f.isSinkAssignment = isAssignment && f.isBufferAccess;

    const callAnc = this.nearestCallAncestor(v);
    if (callAnc) {
      const callee = (this.getName(callAnc) ?? this.getCode(callAnc) ?? "").toLowerCase();
      const code = (this.getCode(callAnc) ?? "").toLowerCase();

      const unbounded = /(strcpy|stpcpy|gets|sprintf|vsprintf)\b/.test(callee) || /(strcpy|gets|sprintf)/.test(code);
      const bounded =
        /(strncpy|strlcpy|snprintf|vsnprintf|memcpy|memmove|fgets)\b/.test(callee) || /(snprintf|strncpy|memcpy|memmove|fgets)/.test(code);

      f.isSinkCallUnbounded = unbounded && !bounded;
      f.isSinkCallBounded = bounded;

      f.callDestinationIndexed = /\[[^\]]+\]/.test(code.split(",")[0] ?? "");
      f.callLengthLinkedToDestination = /\b(sizeof|strlen)\s*\(/.test(code);
      f.callSizeNonConstant = /\b(snprintf|vsnprintf|memcpy|memmove|strncpy)\b/.test(callee) && !/\b\d+\b/.test(code);
      f.callDangerUnbounded = /\b(gets|strcpy|sprintf)\b/.test(callee);
    }

    return f;
  }

  private computeEdgeFeature(def: VertexGeneric, use: VertexGeneric): IDFGEdgeFeature {
    const flow = this.classifyFlow(def, use);
    const guardInfo = this.findNearestGuard(use);
    const hasLowerGuard = this.hasLowerBoundCheck(use);
    const hasUpperGuard = this.hasUpperBoundCheck(use);
    const upperGuardNormalization = this.upperBoundNormalizationFactor(use);

    return {
      flow,
      guard: guardInfo.kind,
      hasLowerGuard,
      hasUpperGuard,
      upperGuardNormalization,
    };
  }

  private classifyFlow(def: VertexGeneric, use: VertexGeneric): IDFGEdgeFeature["flow"] {
    const name = (this.getName(use) ?? this.getCode(use) ?? "").trim();

    // Gather ancestor codes for structural checks
    const startId = use.id["@value"];
    const visited = new Set<number>([startId]);
    const q: number[] = [startId];
    const ancestorCodes: string[] = [];
    let hops = 0;
    while (q.length && hops < 12) {
      const cur = q.shift();
      if (cur == null) break;
      for (const pid of this.getAstParents(cur)) {
        if (visited.has(pid)) continue;
        visited.add(pid);
        const p = this.getNodeById(pid);
        if (!p) continue;
        const c = this.getCode(p);
        if (c) ancestorCodes.push(c);
        q.push(pid);
      }
      hops += 1;
    }

    const anyAncestorMatches = (re: RegExp): boolean => ancestorCodes.some((c) => re.test(c));
    const anyAncestorIncludes = (s: string): boolean => ancestorCodes.some((c) => c.includes(s));

    // 1) Array and pointer contexts
    const nameEsc = this.escapeRe(name);
    //    - Index variable inside brackets [ ... name ... ]
    const indexInBracketsRe = new RegExp(`\\[[^\\]]*\\b${nameEsc}\\b[^\\]]*\\]`);
    if (ancestorCodes.some((c) => indexInBracketsRe.test(c))) return FlowType.INDEX;

    //    - Base variable before subscript: name[ ... ]
    const baseBeforeBracketRe = new RegExp(`\\b${nameEsc}\\s*\\[`);
    if (ancestorCodes.some((c) => baseBeforeBracketRe.test(c))) return FlowType.BASE;

    //    - Pointer deref with offset: *(name + k) -> name is BASE, *(k + name) -> name is INDEX
    const derefWithName = ancestorCodes.find(
      (c) => /\*\s*\([^)]*\)/.test(c) && new RegExp(`\\(.*\\b${nameEsc}\\b.*\\)`).test(c)
    );
    if (derefWithName) {
      const baseSideRe = new RegExp(`\\*\\s*\\(\\s*${nameEsc}\\s*[+-]`);
      const indexSideRe = new RegExp(`[+-]\\s*${nameEsc}\\s*\\)`);
      if (baseSideRe.test(derefWithName)) return FlowType.BASE;
      if (indexSideRe.test(derefWithName)) return FlowType.INDEX;
      // If ambiguous but inside deref with arithmetic, treat as BASE by default
      return FlowType.BASE;
    }

    // 2) Call context: map common libc-style APIs to roles
    const callAnc = this.nearestCallAncestor(use);
    if (callAnc) {
      const callee = (this.getName(callAnc) ?? this.getCode(callAnc) ?? "").toLowerCase();
      const callCode = (this.getCode(callAnc) ?? "").trim();

      // Extract args naively: split by first '(' and last ')', then commas
      let args: string[] = [];
      const parenIdx = callCode.indexOf("(");
      const lastParenIdx = callCode.lastIndexOf(")");
      if (parenIdx >= 0 && lastParenIdx > parenIdx) {
        const inside = callCode.slice(parenIdx + 1, lastParenIdx);
        args = inside.split(",").map((s) => s.trim());
      }

      // Find which arg contains the identifier
      const argIndex = args.findIndex((a) => new RegExp(`\\b${this.escapeRe(name)}\\b`).test(a));

      const isInIndexExpr = args.some((a) => new RegExp(`\\[[^\\]]*\\b${this.escapeRe(name)}\\b[^\\]]*\\]`).test(a));
      if (isInIndexExpr) return FlowType.INDEX;

      // memcpy/memmove: (dest, src, size)
      if (/\b(memcpy|memmove)\b/.test(callee)) {
        if (argIndex === 0) return FlowType.BASE;
        if (argIndex === 1) return FlowType.VALUE;
        if (argIndex === 2) return FlowType.SIZE;
      }
      // strncpy/strlcpy/snprintf/vsnprintf: third argument is size
      if (/\b(strncpy|strlcpy|snprintf|vsnprintf)\b/.test(callee)) {
        if (argIndex === 0) return FlowType.BASE;
        if (argIndex === 2) return FlowType.SIZE;
        if (argIndex === 1) return FlowType.VALUE;
      }
      // strcpy/stpcpy/sprintf/gets: dest then src/payload
      if (/\b(strcpy|stpcpy|sprintf|vsprintf|gets)\b/.test(callee)) {
        if (argIndex === 0) return FlowType.BASE;
        if (argIndex >= 1) return FlowType.VALUE;
      }
      // fgets: (buf, size, stream)
      if (/\b(fgets)\b/.test(callee)) {
        if (argIndex === 0) return FlowType.BASE;
        if (argIndex === 1) return FlowType.SIZE;
        if (argIndex === 2) return FlowType.VALUE;
      }
      // read/recv/fread: (fd/stream, buf, count)
      if (/\b(read|recv|fread)\b/.test(callee)) {
        if (argIndex === 1) return FlowType.BASE;
        if (argIndex === 2) return FlowType.SIZE;
      }
      // write/send/fwrite: (fd/stream, buf, count) => buf is VALUE payload
      if (/\b(write|send|fwrite)\b/.test(callee)) {
        if (argIndex === 1) return FlowType.VALUE;
        if (argIndex === 2) return FlowType.SIZE;
      }
      // allocators: args are size/count
      if (/\b(malloc|realloc)\b/.test(callee)) {
        if (argIndex >= 0) return FlowType.SIZE;
      }
      if (/\b(calloc)\b/.test(callee)) {
        if (argIndex === 0 || argIndex === 1) return FlowType.SIZE;
      }
    }

    // 3) Predicate/guard context: decide index vs size by side of comparator
    const pred = this.findFirstPredicateCode(use);
    if (pred && /<|<=|>|>=/.test(pred) && new RegExp(`\\b${this.escapeRe(name)}\\b`).test(pred)) {
      // Find first comparator position and variable position
      const compMatch = /<=|>=|<|>/.exec(pred);
      const idPos = pred.search(new RegExp(`\\b${this.escapeRe(name)}\\b`));
      const compPos = compMatch ? pred.indexOf(compMatch[0]) : -1;
      if (compPos >= 0 && idPos >= 0) {
        // Heuristic: left of comparator => index; right => size
        if (idPos < compPos) return FlowType.INDEX;
        return FlowType.SIZE;
      }
    }

    // 4) Direct dereference without offset likely base usage
    if (anyAncestorIncludes(`*${name}`) || anyAncestorIncludes(`${name}->`) || anyAncestorIncludes(`&${name}[`)) {
      return FlowType.BASE;
    }

    // 5) sizeof/alignof/typeof contexts imply size semantics
    if (anyAncestorMatches(/\b(sizeof|alignof|typeof)\s*\(/i)) {
      return FlowType.SIZE;
    }

    // Default: general value usage
    return FlowType.VALUE;
  }

  private findNearestGuard(n: VertexGeneric): { kind: GuardType } {
    const start = n.id["@value"];
    const visited = new Set<number>([start]);
    const q: number[] = [start];

    while (q.length) {
      const cur = q.shift();
      if (cur == null) break;
      for (const pid of this.getAstParents(cur)) {
        if (visited.has(pid)) continue;
        visited.add(pid);
        const p = this.getNodeById(pid);
        if (!p) continue;
        const lbl = this.getLabel(p);
        if (lbl === "CONTROL_STRUCTURE") {
          const code = (this.getCode(p) ?? "").trim();
          if (/^\s*if\b/i.test(code)) return { kind: GuardType.IF };
          if (/^\s*(for|while|do)\b/i.test(code)) return { kind: GuardType.LOOP };
        }
        q.push(pid);
      }
    }
    return { kind: GuardType.NONE };
  }

  private hasLowerBoundCheck(n: VertexGeneric): boolean {
    const id = this.getName(n) ?? this.getCode(n) ?? "";
    const re = new RegExp(`\\b(${this.escapeRe(id)})\\s*>=?\\s*0|0\\s*<=?\\s*(${this.escapeRe(id)})`);
    return this.scanUpForPredicate(n, re);
  }

  private hasUpperBoundCheck(n: VertexGeneric): boolean {
    const id = this.getName(n) ?? this.getCode(n) ?? "";
    const re = new RegExp(`\\b(${this.escapeRe(id)})\\s*<\\s*[^;]+|\\b(${this.escapeRe(id)})\\s*<=\\s*[^;]+`);
    return this.scanUpForPredicate(n, re);
  }

  private upperBoundNormalizationFactor(n: VertexGeneric): number {
    const code = this.findFirstPredicateCode(n) ?? "";
    if (/\bsizeof\s*\(/.test(code)) return 1.0;
    if (/\b\d+\b/.test(code)) return 1.0;
    return 0.5;
  }

  private scanUpForPredicate(n: VertexGeneric, re: RegExp): boolean {
    const code = this.findFirstPredicateCode(n);
    return code ? re.test(code) : false;
  }

  private findFirstPredicateCode(n: VertexGeneric): string | null {
    const start = n.id["@value"];
    const visited = new Set<number>([start]);
    const q: number[] = [start];

    while (q.length) {
      const cur = q.shift();
      if (cur == null) break;
      for (const pid of this.getAstParents(cur)) {
        if (visited.has(pid)) continue;
        visited.add(pid);
        const p = this.getNodeById(pid);
        if (!p) continue;
        if (this.getLabel(p) === "CONTROL_STRUCTURE") {
          const c = this.getCode(p);
          if (c && /if|for|while|do/.test(c)) return c;
        }
        q.push(pid);
      }
    }
    return null;
  }

  private updateNodeDegrees(nodes: IDFGNode[], edges: IDFGEdge[]): void {
    const byId = new Map<number, IDFGNode>();
    for (const n of nodes) byId.set(n.id, n);

    for (const e of edges) {
      const src = byId.get(e.source);
      const dst = byId.get(e.destination);
      if (src) src.features.outDegreeDFG += 1;
      if (dst) dst.features.inDegreeDFG += 1;
    }
  }

  private getNodeById(id: number): VertexGeneric | null {
    for (const v of this.cpg.export["@value"].vertices) {
      if (v.id["@value"] === id) return v;
    }
    return null;
  }
  private getAstParents(id: number): number[] {
    const out: number[] = [];
    for (const e of this.cpg.export["@value"].edges) {
      if (e.label === "AST" && e.inV["@value"] === id) out.push(e.outV["@value"]);
    }
    return out;
  }
  private getAstChildren(id: number): number[] {
    const out: number[] = [];
    for (const e of this.cpg.export["@value"].edges) {
      if (e.label === "AST" && e.outV["@value"] === id) out.push(e.inV["@value"]);
    }
    return out;
  }
  private getCode(node: VertexGeneric): string | null {
    const arr = this.readPropArray(node, "CODE");
    return Array.isArray(arr) && typeof arr[0] === "string" ? arr[0] : null;
  }
  private getName(node: VertexGeneric): string | null {
    const arr = this.readPropArray(node, "NAME");
    return Array.isArray(arr) && typeof arr[0] === "string" ? arr[0] : null;
  }
  private getLabel(node: VertexGeneric): string {
    return typeof node.label === "string" ? node.label : "<node>";
  }
  private getLineNumber(node: VertexGeneric): number | null {
    const num = (v: unknown): number | null => {
      if (typeof v === "number") return Number.isFinite(v) ? v : null;
      if (typeof v === "string") {
        const n = Number(v);
        return Number.isFinite(n) ? n : null;
      }
      if (v && typeof v === "object" && "@value" in (v as Record<string, unknown>)) {
        return num((v as Record<string, unknown>)["@value"]);
      }
      return null;
    };
    const readLoose = (n: VertexGeneric, key: string): number | null => {
      const props = (n as unknown as { properties?: Record<string, unknown> }).properties;
      const step1 = props ? props[key] : undefined;

      if (step1 && typeof step1 === "object") {
        const outer = (step1 as Record<string, unknown>)["@value"];
        if (outer && typeof outer === "object") {
          const inner = (outer as Record<string, unknown>)["@value"];
          if (Array.isArray(inner) && inner.length > 0) {
            const v = num(inner[0]);
            if (v != null && v > 0) return v;
          }
        }
        const v2 = (step1 as { ["@value"]?: unknown })["@value"];
        const v2n = num(v2);
        if (v2n != null && v2n > 0) return v2n;
      }
      const v3 = num(step1);
      return v3 != null && v3 > 0 ? v3 : null;
    };
    const keys = ["LINE_NUMBER", "START_LINE", "END_LINE", "LINE_NUMBER_END", "LINE"];
    for (const k of keys) {
      const v = readLoose(node, k);
      if (v != null) return v;
    }

    const startId = node.id["@value"];
    const seen = new Set<number>([startId]);
    const tryId = (nid: number): number | null => {
      const n = this.getNodeById(nid);
      if (!n) return null;
      for (const k of keys) {
        const v = readLoose(n, k);
        if (v != null) return v;
      }
      return null;
    };

    {
      const q: number[] = [startId];
      while (q.length) {
        const cur = q.shift();
        if (cur == null) break;
        for (const pid of this.getAstParents(cur)) {
          if (seen.has(pid)) continue;
          seen.add(pid);
          const v = tryId(pid);
          if (v != null) return v;
          q.push(pid);
        }
      }
    }
    {
      const q: number[] = [startId];
      while (q.length) {
        const cur = q.shift();
        if (cur == null) break;
        for (const cid of this.getAstChildren(cur)) {
          if (seen.has(cid)) continue;
          seen.add(cid);
          const v = tryId(cid);
          if (v != null) return v;
          q.push(cid);
        }
      }
    }
    return null;
  }
  private readPropArray(node: VertexGeneric, key: string): unknown[] | null {
    const props = (node as unknown as { properties?: Record<string, unknown> }).properties;
    const step1 = props ? props[key] : undefined;
    if (!step1 || typeof step1 !== "object") return null;
    const outer = (step1 as Record<string, unknown>)["@value"];
    if (!outer || typeof outer !== "object") return null;
    const inner = (outer as Record<string, unknown>)["@value"];
    return Array.isArray(inner) ? inner : null;
  }

  private nearestCallAncestor(n: VertexGeneric): VertexGeneric | null {
    const start = n.id["@value"];
    const visited = new Set<number>([start]);
    const q: number[] = [start];
    while (q.length) {
      const cur = q.shift();
      if (cur == null) break;
      for (const pid of this.getAstParents(cur)) {
        if (visited.has(pid)) continue;
        visited.add(pid);
        const p = this.getNodeById(pid);
        if (!p) continue;
        if (this.getLabel(p) === "CALL") return p;
        q.push(pid);
      }
    }
    return null;
  }

  private inferTemplateType(v: VertexGeneric): TemplateNodeTypes {
    return v.label as TemplateNodeTypes;
  }

  private escapeRe(s: string): string {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }
}
