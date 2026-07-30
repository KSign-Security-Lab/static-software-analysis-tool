// Complexity-reducers applied to a GraphView before rendering:
//   - scopeToMethod : keep only one function's nodes (kills node count)
//   - contract      : drop "noise" nodes, reconnecting edges through them
//   - neighborhood  : focus a node + its N-hop neighbours
//   - search        : node ids matching a query
// All are pure transforms over GraphView, composable in any order.

import type { GraphView, ParsedCpg, ViewEdge, ViewNode } from "./types";

export interface MethodRef {
  id: string;
  name: string;
  file: string;
}

/** Internal (user-defined) methods, for the function picker. */
export function internalMethods(cpg: ParsedCpg): MethodRef[] {
  const out: MethodRef[] = [];
  for (const n of cpg.nodes.values()) {
    if (n.label !== "METHOD") continue;
    if (!n.name || n.name.startsWith("<")) continue;
    if (n.props.IS_EXTERNAL === true) continue;
    out.push({ id: n.id, name: n.name, file: String(n.props.FILENAME ?? "") });
  }
  return out.sort((a, b) => a.name.localeCompare(b.name));
}

// Joern labels / operator calls that add noise without structural meaning.
const NOISE_LABELS = new Set([
  "LITERAL",
  "BLOCK",
  "METHOD_RETURN",
  "METHOD_PARAMETER_OUT",
  "TYPE",
  "TYPE_DECL",
  "TYPE_REF",
  "MODIFIER",
  "NAMESPACE",
  "NAMESPACE_BLOCK",
  "FILE",
  "META_DATA",
  "IMPORT",
  "DEPENDENCY",
  "UNKNOWN",
]);

export function isNoise(n: ViewNode): boolean {
  if (NOISE_LABELS.has(n.label)) return true;
  if (n.label === "CALL" && n.name.startsWith("<operator>")) return true;
  return false;
}

function induce(base: GraphView, nodeIds: Set<string>, edges: ViewEdge[]): GraphView {
  return {
    ...base,
    nodes: base.nodes.filter((n) => nodeIds.has(n.id)),
    edges: edges.filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target)),
  };
}

export function scopeToMethod(view: GraphView, cpg: ParsedCpg, methodId: string): GraphView {
  const ids = new Set<string>();
  for (const n of view.nodes) {
    if (n.id === methodId || cpg.methodOf(n.id) === methodId) ids.add(n.id);
  }
  return induce(view, ids, view.edges);
}

/** For the (already method-level) CG view: keep the method + direct neighbours. */
export function scopeCallGraph(view: GraphView, methodId: string): GraphView {
  const edges = view.edges.filter((e) => e.source === methodId || e.target === methodId);
  const ids = new Set<string>([methodId]);
  for (const e of edges) {
    ids.add(e.source);
    ids.add(e.target);
  }
  return induce(view, ids, edges);
}

/**
 * Remove nodes failing `keep`, reconnecting survivors through the dropped nodes
 * (transitive contraction) so the graph stays connected and meaningful.
 */
export function contract(view: GraphView, keep: (n: ViewNode) => boolean): GraphView {
  const kept = new Set(view.nodes.filter(keep).map((n) => n.id));
  if (kept.size === view.nodes.length) return view;

  const out = new Map<string, ViewEdge[]>();
  for (const e of view.edges) {
    if (!out.has(e.source)) out.set(e.source, []);
    out.get(e.source)!.push(e);
  }

  const edges: ViewEdge[] = [];
  const seen = new Set<string>();
  for (const src of kept) {
    const stack = [...(out.get(src) ?? [])];
    const visited = new Set<string>();
    while (stack.length) {
      const e = stack.pop()!;
      if (visited.has(e.target)) continue;
      visited.add(e.target);
      if (kept.has(e.target)) {
        const key = `${src}->${e.target}`;
        if (!seen.has(key)) {
          seen.add(key);
          edges.push({ id: `k${edges.length}`, source: src, target: e.target, label: e.label });
        }
      } else {
        stack.push(...(out.get(e.target) ?? []));
      }
    }
  }
  return { ...view, nodes: view.nodes.filter((n) => kept.has(n.id)), edges };
}

/** Node ids whose name/code/label match the query (case-insensitive). */
export function searchNodes(view: GraphView, query: string): Set<string> {
  const q = query.trim().toLowerCase();
  const hits = new Set<string>();
  if (!q) return hits;
  for (const n of view.nodes) {
    if (
      n.name.toLowerCase().includes(q) ||
      n.code.toLowerCase().includes(q) ||
      n.label.toLowerCase().includes(q)
    ) {
      hits.add(n.id);
    }
  }
  return hits;
}

/** Keep a node and everything within `hops` edges of it (undirected). */
export function neighborhood(view: GraphView, nodeId: string, hops: number): GraphView {
  const adj = new Map<string, string[]>();
  for (const e of view.edges) {
    (adj.get(e.source) ?? adj.set(e.source, []).get(e.source)!).push(e.target);
    (adj.get(e.target) ?? adj.set(e.target, []).get(e.target)!).push(e.source);
  }
  const keep = new Set<string>([nodeId]);
  let frontier = [nodeId];
  for (let h = 0; h < hops; h++) {
    const next: string[] = [];
    for (const id of frontier) {
      for (const nb of adj.get(id) ?? []) {
        if (!keep.has(nb)) {
          keep.add(nb);
          next.push(nb);
        }
      }
    }
    frontier = next;
  }
  return induce(view, keep, view.edges);
}
