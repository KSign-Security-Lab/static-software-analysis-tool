// Project the four graph views out of a parsed CPG, purely by edge label —
// the same "extract by structure, not text" idea F2-A uses.

import type { CpgEdge, CpgViewKey, GraphView, ParsedCpg, ViewEdge, ViewNode } from "./types";

function toViewNode(cpg: ParsedCpg, id: string): ViewNode | undefined {
  const n = cpg.nodes.get(id);
  if (!n) return undefined;
  return { id: n.id, label: n.label, name: n.name, code: n.code, line: n.line, props: n.props };
}

/** Build a view from a set of directed edges, inducing the touched node set. */
function induced(
  cpg: ParsedCpg,
  key: CpgViewKey,
  title: string,
  description: string,
  edges: ViewEdge[],
  extraNodeIds: string[] = [],
): GraphView {
  const ids = new Set<string>(extraNodeIds);
  for (const e of edges) {
    ids.add(e.source);
    ids.add(e.target);
  }
  const nodes: ViewNode[] = [];
  for (const id of ids) {
    const vn = toViewNode(cpg, id);
    if (vn) nodes.push(vn);
  }
  return { key, title, description, nodes, edges };
}

function byLabel(cpg: ParsedCpg, labels: string[]): CpgEdge[] {
  const out: CpgEdge[] = [];
  for (const l of labels) out.push(...(cpg.edgesByLabel.get(l) ?? []));
  return out;
}

export function astView(cpg: ParsedCpg): GraphView {
  const edges: ViewEdge[] = byLabel(cpg, ["AST"]).map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: "",
  }));
  return induced(cpg, "ast", "AST", "Syntax tree — AST edges (parent → child).", edges);
}

export function cfgView(cpg: ParsedCpg): GraphView {
  const edges: ViewEdge[] = byLabel(cpg, ["CFG"]).map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: "",
  }));
  return induced(
    cpg,
    "cfg",
    "CFG",
    "Control-flow inside functions — CFG edges (execution order).",
    edges,
  );
}

export function dfgView(cpg: ParsedCpg): GraphView {
  const edges: ViewEdge[] = byLabel(cpg, ["REACHING_DEF"]).map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.variable ?? "",
  }));
  return induced(
    cpg,
    "dfg",
    "DFG",
    "Data flow — REACHING_DEF edges (def → use); edge label = variable.",
    edges,
  );
}

/**
 * Call graph between functions. Each Joern CALL edge goes call-site → callee
 * METHOD; we lift the call-site to its enclosing METHOD so the view is
 * method → method (deduplicated). Isolated internal methods are kept as nodes.
 */
export function cgView(cpg: ParsedCpg): GraphView {
  const seen = new Set<string>();
  const edges: ViewEdge[] = [];
  for (const e of cpg.edgesByLabel.get("CALL") ?? []) {
    const caller = cpg.methodOf(e.source);
    const callee = e.target; // already a METHOD
    if (!caller || !callee) continue;
    const k = `${caller}->${callee}`;
    if (seen.has(k)) continue;
    seen.add(k);
    edges.push({ id: `cg${edges.length}`, source: caller, target: callee, label: "calls" });
  }
  const methodIds: string[] = [];
  for (const [id, n] of cpg.nodes) if (n.label === "METHOD") methodIds.push(id);
  return induced(
    cpg,
    "cg",
    "CG",
    "Call graph between functions — who calls whom (CALL edges lifted to methods).",
    edges,
    methodIds,
  );
}

export function cpgView(cpg: ParsedCpg): GraphView {
  const edges: ViewEdge[] = cpg.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label,
  }));
  const allIds = Array.from(cpg.nodes.keys());
  return induced(
    cpg,
    "cpg",
    "CPG",
    "Full Code Property Graph — all vertices and edges.",
    edges,
    allIds,
  );
}

// Candidate edge labels the user can toggle per drill-down tab (CG is special —
// its edges are lifted to method level, so it has no toggles). `on` = default.
export const EDGE_TABS: Record<Exclude<CpgViewKey, "cg">, { label: string; on: boolean }[]> = {
  ast: [{ label: "AST", on: true }],
  cfg: [
    { label: "CFG", on: true },
    { label: "DOMINATE", on: false },
    { label: "POST_DOMINATE", on: false },
    { label: "CDG", on: false },
  ],
  dfg: [
    { label: "REACHING_DEF", on: true },
    { label: "REF", on: false },
    { label: "ARGUMENT", on: false },
  ],
  cpg: [
    { label: "AST", on: true },
    { label: "CFG", on: true },
    { label: "REACHING_DEF", on: true },
    { label: "CALL", on: true },
    { label: "REF", on: false },
    { label: "DOMINATE", on: false },
    { label: "CDG", on: false },
    { label: "ARGUMENT", on: false },
    { label: "CONDITION", on: false },
  ],
};

const TAB_TITLES: Record<CpgViewKey, { title: string; description: string }> = {
  cpg: { title: "CPG", description: "Code Property Graph — pick which edge layers to overlay." },
  ast: { title: "AST", description: "Syntax tree — AST edges (parent → child)." },
  cg: { title: "CG", description: "Call graph between functions — who calls whom." },
  dfg: { title: "DFG", description: "Data flow — REACHING_DEF (def → use); label = variable." },
  cfg: { title: "CFG", description: "Control flow inside functions — execution order." },
};

/** Build a view from an arbitrary set of edge labels (drives the edge toggles). */
export function buildViewFromLabels(cpg: ParsedCpg, key: CpgViewKey, labels: string[]): GraphView {
  const edges: ViewEdge[] = [];
  for (const l of labels) {
    for (const e of cpg.edgesByLabel.get(l) ?? []) {
      edges.push({ id: e.id, source: e.source, target: e.target, label: e.variable ?? "" });
    }
  }
  const t = TAB_TITLES[key];
  return induced(cpg, key, t.title, t.description, edges);
}

export function buildViews(cpg: ParsedCpg): Record<CpgViewKey, GraphView> {
  return {
    cpg: cpgView(cpg),
    ast: astView(cpg),
    cg: cgView(cpg),
    dfg: dfgView(cpg),
    cfg: cfgView(cpg),
  };
}
