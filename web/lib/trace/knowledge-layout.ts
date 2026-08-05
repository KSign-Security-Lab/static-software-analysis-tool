import dagre from "dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type { Community, KnowledgeEdge, KnowledgeGraph, KnowledgeNode } from "@/lib/api/types";
import type { FileCount } from "@/lib/model/finding";

/**
 * Laying out the code's own graph.
 *
 * Separate from lib/trace/layout.ts, which draws the agent's pipeline: that
 * one has a fixed shape of eleven nodes and hand-tuned back edges, this one
 * has whatever the indexer found. Generalising the two would leave neither
 * doing its own job well.
 */

export const KNOWLEDGE_NODE_W = 168;
export const KNOWLEDGE_NODE_H = 40;

/**
 * Above this, units are collapsed into their communities.
 *
 * graphify says it plainly: a hairball of two thousand nodes is a screensaver,
 * and the useful question is "what groups exist and what is in them". Below it
 * there is no hairball to avoid, and collapsing would hide the answer instead.
 */
export const UNIT_LIMIT = 60;

/** Above this, even the community view is a list rather than a drawing. */
export const DRAW_LIMIT = 400;

export type Progress = "pending" | "running" | "done" | null;

export interface KnowledgeNodeData extends Record<string, unknown> {
  label: string;
  file: string;
  kind: "file" | "unit" | "community";
  members: number;
  severity: string | null;
  findings: number;
  progress: Progress;
  selected: boolean;
}

export interface PaintOptions {
  /** Findings keyed by chunk id, which is exactly the node id. */
  counts: Map<string, FileCount>;
  /** Chunk ids queued, running and finished, from the live inspection state. */
  pending: Set<string>;
  running: Set<string>;
  selected: string | null;
  /** Expanded communities, when the view is collapsed. */
  expanded: Set<number>;
}

export interface Laid {
  nodes: Node<KnowledgeNodeData>[];
  edges: Edge[];
  /** True when units were collapsed, so the caller can say so. */
  collapsed: boolean;
}

function progressOf(id: string, options: PaintOptions): Progress {
  if (options.running.has(id)) return "running";
  if (options.pending.has(id)) return "pending";
  return null;
}

/**
 * Which nodes to draw, and the edges between them.
 *
 * When collapsed, a community becomes one node and the edges between two
 * communities are merged into one -- otherwise the same relationship is drawn
 * once per member pair and the picture is denser than the uncollapsed one.
 */
function project(graph: KnowledgeGraph, options: PaintOptions) {
  const collapse = graph.nodes.length > UNIT_LIMIT;
  if (!collapse) return { nodes: graph.nodes, edges: graph.edges, communities: [] as Community[], collapsed: false };

  const shownUnits = new Set(
    graph.nodes.filter((node) => node.community !== null && options.expanded.has(node.community)).map((n) => n.id),
  );
  const communityOf = new Map(graph.nodes.map((node) => [node.id, node.community]));

  const nodes = graph.nodes.filter((node) => shownUnits.has(node.id));
  const communities = graph.communities.filter((c) => !options.expanded.has(c.id));

  // An edge is drawn between whatever each end resolves to -- itself if
  // expanded, its community otherwise. Self-loops after that collapse are
  // dropped: a community calling itself is not information.
  const seen = new Set<string>();
  const edges: KnowledgeEdge[] = [];
  for (const edge of graph.edges) {
    const src = shownUnits.has(edge.src) ? edge.src : `c${communityOf.get(edge.src)}`;
    const dst = shownUnits.has(edge.dst) ? edge.dst : `c${communityOf.get(edge.dst)}`;
    if (src === dst) continue;
    const key = `${src}->${dst}:${edge.provenance}`;
    if (seen.has(key)) continue;
    seen.add(key);
    edges.push({ ...edge, src, dst });
  }

  return { nodes, edges, communities, collapsed: true };
}

export function layoutKnowledge(graph: KnowledgeGraph, options: PaintOptions): Laid {
  const { nodes: units, edges, communities, collapsed } = project(graph, options);

  const graphed = new dagre.graphlib.Graph();
  graphed.setDefaultEdgeLabel(() => ({}));
  graphed.setGraph({ rankdir: "LR", nodesep: 18, ranksep: 56, marginx: 16, marginy: 16 });

  const data = new Map<string, KnowledgeNodeData>();

  for (const unit of units as KnowledgeNode[]) {
    const count = options.counts.get(unit.id);
    data.set(unit.id, {
      label: unit.label,
      file: unit.file,
      kind: unit.kind,
      members: 0,
      severity: count?.worst ?? null,
      findings: count?.total ?? 0,
      progress: progressOf(unit.id, options),
      selected: options.selected === unit.id,
    });
    graphed.setNode(unit.id, { width: KNOWLEDGE_NODE_W, height: KNOWLEDGE_NODE_H });
  }

  for (const community of communities) {
    const worst = community.members
      .map((id) => options.counts.get(id))
      .filter(Boolean)
      .sort((a, b) => (a!.worst ?? "z").localeCompare(b!.worst ?? "z"))[0];
    const id = `c${community.id}`;
    data.set(id, {
      label: community.label,
      file: community.files[0] ?? "",
      kind: "community",
      members: community.members.length,
      severity: worst?.worst ?? null,
      findings: community.members.reduce((total, member) => total + (options.counts.get(member)?.total ?? 0), 0),
      progress: community.members.some((m) => options.running.has(m))
        ? "running"
        : community.members.some((m) => options.pending.has(m))
          ? "pending"
          : null,
      selected: options.selected === id,
    });
    graphed.setNode(id, { width: KNOWLEDGE_NODE_W, height: KNOWLEDGE_NODE_H });
  }

  for (const edge of edges) {
    if (data.has(edge.src) && data.has(edge.dst)) graphed.setEdge(edge.src, edge.dst);
  }

  dagre.layout(graphed);

  return {
    collapsed,
    nodes: [...data.entries()].map(([id, node]) => {
      const placed = graphed.node(id);
      return {
        id,
        type: "knowledgeNode",
        position: {
          x: (placed?.x ?? 0) - KNOWLEDGE_NODE_W / 2,
          y: (placed?.y ?? 0) - KNOWLEDGE_NODE_H / 2,
        },
        data: node,
      };
    }),
    edges: edges
      .filter((edge) => data.has(edge.src) && data.has(edge.dst))
      .map((edge, index) => ({
        id: `${edge.src}->${edge.dst}-${index}`,
        source: edge.src,
        target: edge.dst,
        // An edge the parser resolved and one guessed from a README are not
        // the same claim, and the drawing must not flatten them.
        style: {
          stroke: "var(--line-3)",
          strokeDasharray: edge.provenance === "inferred" ? "4 3" : undefined,
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: "var(--line-3)", width: 12, height: 12 },
      })),
  };
}
