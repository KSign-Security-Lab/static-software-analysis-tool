/**
 * The inspection graph, laid out.
 *
 * Not `lib/layout.ts`: that one is for Joern's CPG, with a hardcoded colour per
 * vertex label and a per-view direction table, none of which applies here. This
 * one has a single shape to draw and hands the drawing itself to a custom node,
 * so the layout stays about position.
 *
 * dagre rather than a hand-rolled pass. The old view assigned every node the
 * same x, which happened to work only because the graph is currently one line
 * and a loop -- two nodes at the same depth landed exactly on top of each other.
 */

import dagre from "dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type { GraphShape } from "@/lib/api/studio";

// Must match `.gx-node` in studio.css. dagre lays out against these numbers
// and the DOM renders against those, so a disagreement is nodes that overlap
// by exactly the difference.
export const NODE_W = 150;
export const NODE_H = 54;

/** LangGraph's own markers. Drawn, but as terminals rather than as work. */
export const TERMINALS = new Set(["__start__", "__end__"]);

export interface GraphNodeData extends Record<string, unknown> {
  name: string;
  terminal: boolean;
  visits: number;
  averageMs: number | null;
  /** How many tasks of this node are in flight. Several, once a wave fans out. */
  running: number;
  queued: boolean;
  /** An interrupt before this node runs, and one after it has written. */
  before: boolean;
  after: boolean;
  /** Laid out left to right, so the node's in and out ports face sideways. */
  across: boolean;
  onInterrupt?: (node: string, when: "before" | "after") => void;
}

/** Per-node run facts, so the shape can carry what actually happened on it. */
export interface NodeStats {
  visits: number;
  averageMs: number | null;
}

export interface LaidOutGraph {
  nodes: Node<GraphNodeData>[];
  edges: Edge[];
  width: number;
  height: number;
}

export function layoutGraph(
  shape: GraphShape,
  options: {
    stats?: Map<string, NodeStats>;
    running?: string[];
    queued?: string[];
    before?: string[];
    after?: string[];
    onInterrupt?: (node: string, when: "before" | "after") => void;
    /** Left to right suits a wide strip; top to bottom suits a tall canvas. */
    direction?: "LR" | "TB";
  } = {},
): LaidOutGraph {
  const {
    stats,
    running = [],
    queued = [],
    before = [],
    after = [],
    onInterrupt,
    direction = "TB",
  } = options;
  const across = direction === "LR";

  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: direction,
    // Tight within a rank too, and for a sharper reason: laid out left to
    // right, the specialists stack vertically, and five stacked nodes are
    // what the fitted zoom is actually limited by -- not the seven ranks.
    nodesep: across ? 14 : 44,
    // Tight across: the pipeline is seven ranks wide now, and every pixel
    // between them is a pixel off the zoom the whole thing gets fitted to.
    ranksep: across ? 34 : 44,
    marginx: 28,
    marginy: 24,
  });

  const present = new Set(shape.nodes);
  shape.nodes.forEach((name) => graph.setNode(name, { width: NODE_W, height: NODE_H }));

  const edges = shape.edges.filter((e) => present.has(e.source) && present.has(e.target));
  const back = backEdges(shape);
  const forward = edges.filter((e) => !back.has(edgeId(e)));

  // The loop is laid out as if it were not there. Left in, dagre has to break
  // the cycle itself, and it does so by picking a node to demote -- which drags
  // the return path straight down the middle, through everything.
  forward.forEach((e) => graph.setEdge(e.source, e.target));

  // With the loop gone, `verify` has nowhere to go and floats at the bottom
  // beside `__end__` rather than above it. A layout-only edge puts the sink
  // where a reader looks for it; nothing draws this.
  const end = shape.nodes.find((n) => n === "__end__");
  if (end) {
    for (const name of sinks(shape.nodes, forward, end)) graph.setEdge(name, end);
  }

  dagre.layout(graph);

  // Rank as a row number, not as a coordinate: "one step on" has to mean the
  // same thing whatever the node sizes and spacing happen to be.
  const along = (name: string) => (across ? graph.node(name).x : graph.node(name).y);
  const rows = [...new Set(shape.nodes.map(along))].sort((a, b) => a - b);
  const rank = new Map(shape.nodes.map((name) => [name, rows.indexOf(along(name))]));

  const queuedSet = new Set(queued);
  const beforeSet = new Set(before);
  const afterSet = new Set(after);

  const nodes: Node<GraphNodeData>[] = shape.nodes.map((name) => {
    const at = graph.node(name);
    const stat = stats?.get(name);
    return {
      id: name,
      type: "studioNode",
      // dagre positions by centre; React Flow places by top-left corner.
      position: { x: at.x - NODE_W / 2, y: at.y - NODE_H / 2 },
      data: {
        name,
        terminal: TERMINALS.has(name),
        visits: stat?.visits ?? 0,
        averageMs: stat?.averageMs ?? null,
        running: running.filter((node) => node === name).length,
        queued: queuedSet.has(name),
        before: beforeSet.has(name),
        after: afterSet.has(name),
        across,
        onInterrupt,
      },
      draggable: false,
      selectable: !TERMINALS.has(name),
    };
  });

  return {
    nodes,
    edges: edges.map((e) => {
      const looping = back.has(edgeId(e));
      // An edge that skips a rank cannot be drawn down the column without
      // crossing whatever it skipped over. Returns go up the right, early exits
      // down the left, and the column between them stays a straight line.
      const skips = (rank.get(e.target) ?? 0) - (rank.get(e.source) ?? 0) > 1;
      // Whichever way the flow runs, returns leave on one side of it and early
      // exits on the other, so neither crosses the line of steps between them.
      const side = looping ? (across ? "bottom" : "right") : skips ? (across ? "top" : "left") : null;

      return {
        id: edgeId(e),
        source: e.source,
        target: e.target,
        ...(side ? { sourceHandle: `${side}-out`, targetHandle: `${side}-in` } : {}),
        type: "smoothstep",
        pathOptions: { borderRadius: 12 },
        markerEnd: { type: MarkerType.ArrowClosed, width: 13, height: 13 },
        className: [
          "gx-edge",
          e.conditional ? "is-conditional" : "",
          looping ? "is-loop" : "",
        ]
          .filter(Boolean)
          .join(" "),
        style: e.conditional ? { strokeDasharray: "4 4" } : undefined,
      };
    }),
    width: graph.graph().width ?? 0,
    height: graph.graph().height ?? 0,
  };
}

function edgeId(edge: { source: string; target: string }): string {
  return `${edge.source}->${edge.target}`;
}

/**
 * The edges that close a cycle, by a depth-first walk from the entry.
 *
 * An edge into a node still on the stack is a return to somewhere we came
 * from. Which edges those are is not a property of the drawing -- it is what
 * distinguishes `verify -> plan` from every other edge in the graph.
 */
export function backEdges(shape: GraphShape): Set<string> {
  const out = new Map<string, string[]>();
  for (const edge of shape.edges) out.set(edge.source, [...(out.get(edge.source) ?? []), edge.target]);

  const OPEN = 1;
  const CLOSED = 2;
  const state = new Map<string, number>();
  const back = new Set<string>();

  const visit = (name: string): void => {
    state.set(name, OPEN);
    for (const next of out.get(name) ?? []) {
      const seen = state.get(next);
      if (seen === OPEN) back.add(`${name}->${next}`);
      else if (seen === undefined) visit(next);
    }
    state.set(name, CLOSED);
  };

  // From the entry first, so the walk follows the direction the graph runs in
  // and the return edge is the one found closing the loop.
  const entry = shape.nodes.includes("__start__") ? ["__start__", ...shape.nodes] : shape.nodes;
  for (const name of entry) if (!state.has(name)) visit(name);
  return back;
}

/** Nodes with nowhere left to go once the loop is set aside. */
function sinks(nodes: string[], forward: { source: string }[], end: string): string[] {
  const hasNext = new Set(forward.map((e) => e.source));
  return nodes.filter((name) => name !== end && !TERMINALS.has(name) && !hasNext.has(name));
}

/**
 * How often each node ran and how long it took, from this run's own spans.
 *
 * The counts are what turn a diagram into a picture of a run: the same five
 * nodes look very different after one chunk and after forty.
 */
export function statsFromSpans(spans: { name: string; kind: string; latency_ms: number | null }[]): Map<string, NodeStats> {
  const totals = new Map<string, { visits: number; ms: number; timed: number }>();

  for (const span of spans) {
    if (span.kind !== "chain") continue;
    // A node span is named for its node, sometimes with the chunk appended.
    const name = span.name.split(":")[0];
    const row = totals.get(name) ?? { visits: 0, ms: 0, timed: 0 };
    row.visits += 1;
    if (span.latency_ms !== null) {
      row.ms += span.latency_ms;
      row.timed += 1;
    }
    totals.set(name, row);
  }

  const out = new Map<string, NodeStats>();
  for (const [name, row] of totals) {
    out.set(name, { visits: row.visits, averageMs: row.timed > 0 ? Math.round(row.ms / row.timed) : null });
  }
  return out;
}
