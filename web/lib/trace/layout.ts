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

import type { GraphShape } from "@/lib/api/types";
import type { Point } from "./edge-path";

// dagre lays out against these numbers and the DOM renders against them, so a
// disagreement is nodes that overlap by exactly the difference.
//
// Trimmed from 150x54 to pay for the room the routing needs, then given the height
// back for the tags -- laid out left to right the fit is limited by width, so the
// extra row costs nothing at all. Eight ranks laid out
// left to right are already wider than the pane they are fitted into, so every
// pixel of node is a pixel off the zoom -- and the labels are `plan`, `injection`,
// `locate`. Net effect measured on the real graph: the canvas is *smaller* than it
// was before routing, so the fitted zoom went up rather than down.
export const NODE_W = 124;
export const NODE_H = 64;

/** One tool name in the list a node grows to hold. Matches text-2xs, leading-tight. */
const TOOL_ROW_H = 11;

/**
 * Past this a box is a wall of names rather than a list.
 *
 * Ten today, all of them `gather`'s. The cap is for the list that grows later:
 * a node tall enough to be the canvas is a worse answer than a truncated one.
 */
const TOOLS_SHOWN = 12;

/** How tall a box has to be to hold what it says. */
export function heightOf(toolNames: string[]): number {
  if (toolNames.length === 0) return NODE_H;
  const rows = Math.min(toolNames.length, TOOLS_SHOWN) + (toolNames.length > TOOLS_SHOWN ? 1 : 0);
  return NODE_H + rows * TOOL_ROW_H;
}

/**
 * One character of a tool name, and the padding around the list.
 *
 * Measured on the rendered graph rather than derived: 12px monospace, and the
 * name sits inside the row's own padding and the box's. At 124 the longest name
 * wanted 116px of a 106px row and lost ten to an ellipsis -- and a truncated
 * `search_seman…` is most of the way back to the count it replaced.
 */
const TOOL_CHAR_W = 7.3;
const TOOL_CHROME_W = 26;

/** Past this a box is wider than the rank it sits in. */
const MAX_NODE_W = 190;

/** How wide a box has to be to hold its names without an ellipsis. */
export function widthOf(toolNames: string[]): number {
  if (toolNames.length === 0) return NODE_W;
  const longest = Math.max(...toolNames.slice(0, TOOLS_SHOWN).map((name) => name.length));
  return Math.min(MAX_NODE_W, Math.max(NODE_W, Math.ceil(longest * TOOL_CHAR_W + TOOL_CHROME_W)));
}

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
  /**
   * The steps this node runs, if any.
   *
   * Empty means deterministic: `plan`, `context`, `skip`, `locate` and `reduce`
   * never call a model. They looked exactly like the ones that do, which is a fair
   * thing to be confused by -- half the boxes in the graph are plain Python and
   * nothing said so.
   */
  steps: string[];
  /** The most tools any of its steps may call. `gather` is the only one with any. */
  tools: number;
  /**
   * What those tools are called.
   *
   * A count was all the drawing ever said, and a count cannot tell you the run
   * can search semantically -- which is the question that sent someone looking
   * for a box that was never going to exist, because a tool is not a step.
   */
  toolNames: string[];
  /** What the box has to be to hold its names. dagre was laid out against these. */
  height: number;
  width: number;
  /**
   * Whether the step roster was available to say.
   *
   * Absent on a page that has not loaded it yet, and a node tagged `code` because
   * the answer had not arrived would be a lie rather than a gap.
   */
  roster: boolean;
  /** Laid out left to right, so the node's in and out ports face sideways. */
  across: boolean;
  onInterrupt?: (node: string, when: "before" | "after") => void;
}

/** Per-node run facts, so the shape can carry what actually happened on it. */
export interface NodeStats {
  visits: number;
  averageMs: number | null;
}

/** What a routed edge needs: the polyline dagre computed while laying out. */
export interface RoutedEdgeData extends Record<string, unknown> {
  points: Point[];
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
    // Laid out left to right, the specialists stack vertically, and five stacked
    // nodes are what the fitted zoom is limited by -- not the eight ranks. Kept
    // close, but not so close that a route bending between two of them has no
    // room to be seen doing it.
    nodesep: across ? 20 : 40,
    // Every pixel between ranks is a pixel off the zoom the whole thing gets
    // fitted to, and also the room an edge has to leave one node and arrive at
    // another without running along its edge. 34 was the former alone.
    ranksep: across ? 44 : 44,
    marginx: 28,
    marginy: 24,
  });

  // Which steps run in which node, off the roster the API serves with the shape.
  // A list because nothing guarantees one step per node, and the drawing should
  // not be the thing that discovers otherwise.
  //
  // Read before the layout, not after it: a node holding ten tool names is
  // taller than one holding none, and dagre has to be told that before it
  // decides where anything goes.
  const steps = shape.steps ?? [];
  const byNode = new Map<string, typeof steps>();
  for (const step of steps) byNode.set(step.node, [...(byNode.get(step.node) ?? []), step]);

  /** Every tool the node's steps may reach for, in the order they are offered. */
  const toolsOf = (name: string): string[] => {
    const seen = new Set<string>();
    for (const step of byNode.get(name) ?? []) {
      for (const tool of step.tools) seen.add(tool.name);
    }
    return [...seen];
  };

  const present = new Set(shape.nodes);
  const sizes = new Map(
    shape.nodes.map((name) => {
      const names = toolsOf(name);
      return [name, { width: widthOf(names), height: heightOf(names) }] as const;
    }),
  );
  const sizeOf = (name: string) => sizes.get(name) ?? { width: NODE_W, height: NODE_H };
  shape.nodes.forEach((name) => graph.setNode(name, { ...sizeOf(name) }));

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

  const queuedSet = new Set(queued);
  const beforeSet = new Set(before);
  const afterSet = new Set(after);

  const nodes: Node<GraphNodeData>[] = shape.nodes.map((name) => {
    const at = graph.node(name);
    const stat = stats?.get(name);
    const mine = byNode.get(name) ?? [];
    const { width, height } = sizeOf(name);
    return {
      id: name,
      type: "studioNode",
      // dagre positions by centre; React Flow places by top-left corner. The
      // size is this node's own, or a box that grew sits half a row off its
      // edges and the routes arrive at where it used to be.
      position: { x: at.x - width / 2, y: at.y - height / 2 },
      data: {
        name,
        terminal: TERMINALS.has(name),
        visits: stat?.visits ?? 0,
        averageMs: stat?.averageMs ?? null,
        running: running.filter((node) => node === name).length,
        queued: queuedSet.has(name),
        before: beforeSet.has(name),
        after: afterSet.has(name),
        steps: mine.map((step) => step.step),
        tools: Math.max(0, ...mine.map((step) => step.tools.length)),
        toolNames: toolsOf(name),
        height,
        width,
        roster: steps.length > 0,
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
      // dagre routed every edge it was given, around whatever lies between the
      // ends: a dummy node per rank crossed, and the points are a path through
      // the gaps. Drawing that is the difference between an edge that goes where
      // there is room and one that takes the shortest line through a node.
      //
      // Two edges skipped a rank here -- `context -> skip` and `locate -> reduce`
      // -- and both used to be shoved into one hand-picked lane above the flow,
      // which is to say they were drawn on top of each other.
      const routed = looping ? undefined : (graph.edge(e.source, e.target)?.points as Point[] | undefined);

      // The loop is not in the dagre graph -- see above -- so nothing routed it.
      // It keeps the handles across the flow, which is the one lane it can take
      // without cutting back through every step it is returning past.
      const side = looping ? (across ? "bottom" : "right") : null;

      return {
        id: edgeId(e),
        source: e.source,
        target: e.target,
        ...(side ? { sourceHandle: `${side}-out`, targetHandle: `${side}-in` } : {}),
        ...(routed && routed.length > 1
          ? { type: "routed", data: { points: routed } satisfies RoutedEdgeData }
          : { type: "smoothstep", pathOptions: { borderRadius: 12 } }),
        markerEnd: { type: MarkerType.ArrowClosed, width: 13, height: 13 },
        className: [
          "gx-edge",
          e.conditional ? "is-conditional" : "",
          looping ? "is-loop" : "",
        ]
          .filter(Boolean)
          .join(" "),
        // Dotted means a router decides whether this edge is taken; solid means it
        // always is. That is LangGraph's own distinction -- `add_conditional_edges`
        // against `add_edge` -- and it came through the shape untouched.
        //
        // The loop gets a colour rather than a dash, because it is unconditional
        // too: `reduce -> plan` always runs. `.is-loop` carried no styling at all,
        // so a return through the whole graph looked like one more step.
        style: {
          ...(e.conditional ? { strokeDasharray: "5 4" } : {}),
          ...(looping ? { stroke: "var(--alt)" } : {}),
        },
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
