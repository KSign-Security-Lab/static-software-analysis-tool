import { get, seg, type RequestOptions } from "./client";
import type { KnowledgeEdge, KnowledgeGraph, KnowledgeNode } from "./types";

export function fetchKnowledge(runId: string, options?: RequestOptions): Promise<KnowledgeGraph> {
  return get<KnowledgeGraph>(`/agent/runs/${seg(runId)}/graph`, options);
}

export function adjacency(edges: KnowledgeEdge[]): Map<string, Set<string>> {
  const out = new Map<string, Set<string>>();
  const link = (a: string, b: string) => {
    const set = out.get(a) ?? new Set<string>();
    set.add(b);
    out.set(a, set);
  };
  for (const edge of edges) {
    link(edge.src, edge.dst);
    link(edge.dst, edge.src);
  }
  return out;
}

export function neighbours(graph: KnowledgeGraph, id: string, hops = 1): KnowledgeNode[] {
  const adjacent = adjacency(graph.edges);
  const seen = new Set([id]);
  let frontier = [id];

  for (let hop = 0; hop < hops; hop += 1) {
    const next: string[] = [];
    for (const current of frontier) {
      for (const neighbour of adjacent.get(current) ?? []) {
        if (seen.has(neighbour)) continue;
        seen.add(neighbour);
        next.push(neighbour);
      }
    }
    frontier = next;
    if (!frontier.length) break;
  }

  seen.delete(id);
  const byId = new Map(graph.nodes.map((n) => [n.id, n]));
  return [...seen].map((each) => byId.get(each)).filter((each): each is KnowledgeNode => Boolean(each));
}
