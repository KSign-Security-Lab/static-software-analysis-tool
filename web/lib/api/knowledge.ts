import { get, seg, type RequestOptions } from "./client";
import type { KnowledgeEdge, KnowledgeGraph, KnowledgeNode } from "./types";

/**
 * The code's own graph: units, the calls between them, and the communities
 * those calls fall into.
 *
 * The endpoint has existed since the agent gained an index and has never had a
 * client. Node ids are chunk ids, so this joins directly to `Finding.chunk_id`,
 * `Thread.id` and the pending/wave channels -- which is what makes it the
 * run's spatial index rather than a picture.
 *
 * A 404 means the run was never indexed. That is an ordinary answer, not a
 * failure, so callers should not retry it or raise it to the user.
 */
export function fetchKnowledge(runId: string, options?: RequestOptions): Promise<KnowledgeGraph> {
  return get<KnowledgeGraph>(`/agent/runs/${seg(runId)}/graph`, options);
}

/** Adjacency, both directions, built once for repeated neighbour queries. */
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

/**
 * Everything within `hops` of `id`, excluding `id`.
 *
 * The server can do this (`graphify.neighbours`) but does not expose it over
 * HTTP, and the whole graph is already in the cache -- so a breadth-first walk
 * here saves a round trip per selected finding.
 */
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
