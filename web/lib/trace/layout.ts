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
import { roleOf } from "./process";

// dagre lays out against these numbers and the DOM renders against them, so a
// disagreement is nodes that overlap by exactly the difference.
//
// Wide and short, because the node is a puck with its label beside it rather
// than inside it. That trade is only affordable one way round: the real graph is
// ten ranks deep and six wide at the specialist fan, so laid out top to bottom a
// wide node is paid for six times and a tall one ten. Laid out left to right the
// same numbers put the canvas at 2100px and the fitted zoom back under 0.6 --
// which is the problem this whole change exists to fix. See `direction` below.
export const NODE_W = 160;
export const NODE_H = 52;

/** LangGraph's own markers. Drawn, but as terminals rather than as work. */
export const TERMINALS = new Set(["__start__", "__end__"]);

/**
 * The five nodes that call no model, named.
 *
 * `roleOf` narrates step ids and these run no step, so there is nothing for it
 * to read. Taken from what each one's `node_notes.does` says it does, which is
 * written on the server beside the code that does it.
 */
export const CODE_ROLE: Record<string, string> = {
  // Short enough to fit the 110px the label column has. `다음 차례 고르기`
  // rendered as `다음 차레 고…`, which is a label that has stopped being one.
  plan: "차례 고르기",
  context: "맥락 모으기",
  skip: "건너뛰기",
  locate: "위치 찾기",
  reduce: "결과 쓰기",
};

export interface GraphNodeData extends Record<string, unknown> {
  name: string;
  /**
   * What the node does, in the reader's language.
   *
   * The drawing used to be fourteen machine names -- `triage`, `lens:injection`,
   * `locate` -- with the tag pills as the only other text, and a reader asking
   * "which of these found my bug" had nothing to read. `roleOf` already narrates
   * the agent steps for the decision chain; the deterministic five have no step
   * to narrate, so they are named here from what `node_notes` says they do.
   *
   * The machine name is still on the node, in the line underneath. It is what
   * every other surface calls this thing.
   */
  label: string;
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
   * Outside the chain that produced the finding being read.
   *
   * Set by `StepGraph` rather than by the layout, because it is a property of
   * what the reader is looking at rather than of the compiled graph.
   */
  faded?: boolean;
  /**
   * On that chain, and drawn in accent for it.
   *
   * The counterpart to `faded`, and the pair is deliberate: taking light away
   * from the rest was not enough on its own, because a node at 45% and a node at
   * 100% differ only if you look for it. Colouring the path says which nodes
   * answered the question; dimming the others stops them competing. The
   * reference does both -- one cyan curve through a canvas of grey ones.
   */
  lit?: boolean;
  /**
   * Whether the step roster was available to say.
   *
   * Absent on a page that has not loaded it yet, and a node tagged `code` because
   * the answer had not arrived would be a lie rather than a gap.
   */
  roster: boolean;
  /** Laid out left to right, so the node's in and out ports face sideways. */
  across: boolean;
  /**
   * The nodes this one stands in for, when it stands in for several.
   *
   * Empty on an ordinary node. The five specialists collapse into one because
   * they are five copies of one idea -- see `narrow` -- and this is what the box
   * says it is covering.
   */
  members?: string[];
  /** Which of `members` are on the claim trail being read, so the group can name one. */
  litMembers?: string[];
  /**
   * The run can finish at this node.
   *
   * `__end__` is not drawn any more; it was two ranks and the longest edge on the
   * canvas to say what `plan`'s own router already says. The fact moves onto the
   * node that owns the condition.
   */
  exits?: boolean;
  onInterrupt?: (node: string, when: "before" | "after") => void;
}

/** Per-node run facts, so the shape can carry what actually happened on it. */
export interface NodeStats {
  visits: number;
  averageMs: number | null;
}

/** What a routed edge needs: the polyline dagre computed while laying out. */
export interface RoutedEdgeData extends Record<string, unknown> {
  /** Absent on the loop, which dagre never laid out. The edge falls back to a step path. */
  points?: Point[];
  /**
   * The word that goes on the line.
   *
   * A conditional edge used to be a dashed stroke, which meant nothing without a
   * three-item legend above the canvas -- and the legend cost two lines of a pane
   * that had 334px to draw in. The router's own name on the line it governs says
   * the same thing where it applies, and needs nothing to be read first.
   */
  label?: string;
  /** `loop` colours the return edge; `conditional` keeps the label quiet. */
  tone?: "conditional" | "loop";
  /** Laid out left to right, so the label clears the line by moving up rather than sideways. */
  across?: boolean;
  /** On the chain that produced the finding being read. Drawn in accent. */
  lit?: boolean;
}

export interface LaidOutGraph {
  nodes: Node<GraphNodeData>[];
  edges: Edge[];
  width: number;
  height: number;
  /** The specialists, whether or not they are drawn separately this time. */
  lenses: string[];
}

/** The id of the one node that stands in for all the specialists. */
export const LENS_GROUP = "lens:*";

/**
 * The nodes that run a `lens:` step -- read off the roster, not hardcoded.
 *
 * Five today. They are structurally identical: one step each, the same four
 * tools, one in-edge from `scout` and one out-edge to `locate`. What differs is
 * only which kind of flaw each looks for.
 */
export function lensesOf(shape: GraphShape): string[] {
  const found = new Set(
    (shape.steps ?? []).filter((step) => step.step.startsWith("lens:")).map((step) => step.node),
  );
  return shape.nodes.filter((name) => found.has(name));
}

/**
 * The graph with the parts that only cost the reader taken out.
 *
 * Done to the *shape*, before dagre sees it, because both of these are questions
 * about what is worth drawing rather than about how to draw it -- and a layout
 * that has been handed a smaller graph needs no persuading.
 *
 * Two removals:
 *
 * - The five specialists become one node. That rank was six wide and owned ten
 *   of the twenty-three edges, every one of them fanning out of `scout` and back
 *   into `locate`; it is the single largest source of the tangle, and five boxes
 *   that differ only in a word are not five things to understand.
 * - `__start__` and `__end__` go. They are LangGraph's bookkeeping, they cost two
 *   ranks, and `plan -> __end__` was the longest edge on the canvas -- drawn all
 *   the way down the left gutter to say something `plan`'s own router already
 *   says. The node that can end the run is marked instead.
 */
function narrow(shape: GraphShape, expanded: boolean): { shape: GraphShape; lenses: string[]; exits: Set<string> } {
  const lenses = lensesOf(shape);
  const grouped = !expanded && lenses.length > 1;
  const inGroup = new Set(grouped ? lenses : []);

  // Which nodes could have ended the run, before `__end__` stops being drawn.
  const exits = new Set(
    shape.edges.filter((edge) => edge.target === "__end__").map((edge) => edge.source),
  );

  const rename = (name: string) => (inGroup.has(name) ? LENS_GROUP : name);
  const keep = (name: string) => !TERMINALS.has(name);

  const nodes = [
    ...shape.nodes.filter((name) => keep(name) && !inGroup.has(name)),
    ...(grouped ? [LENS_GROUP] : []),
  ];

  const seen = new Set<string>();
  const edges = shape.edges
    .filter((edge) => keep(edge.source) && keep(edge.target))
    .map((edge) => ({ ...edge, source: rename(edge.source), target: rename(edge.target) }))
    // Five identical fan-out edges become one, and so do the five fan-in edges.
    // Left alone they are five copies of one line between the same two boxes.
    .filter((edge) => {
      if (edge.source === edge.target) return false;
      const id = `${edge.source}->${edge.target}`;
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });

  // The group is placed where its members were, so `plan`'s rank is unchanged and
  // the drawing keeps the order the pipeline actually runs in.
  return { shape: { ...shape, nodes, edges }, lenses, exits };
}

export function layoutGraph(
  full: GraphShape,
  options: {
    stats?: Map<string, NodeStats>;
    running?: string[];
    queued?: string[];
    before?: string[];
    after?: string[];
    onInterrupt?: (node: string, when: "before" | "after") => void;
    /** Left to right suits a wide strip; top to bottom suits a tall canvas. */
    direction?: "LR" | "TB";
    /** Draw the five specialists separately. Collapsed to one node by default. */
    expanded?: boolean;
    /** The specialists on the claim trail being read, so the group can name one. */
    litLenses?: string[];
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
    expanded = false,
    litLenses = [],
  } = options;
  const across = direction === "LR";

  const { shape, lenses, exits } = narrow(full, expanded);
  const grouped = new Set(shape.nodes.includes(LENS_GROUP) ? lenses : []);

  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({
    rankdir: direction,
    nodesep: across ? 18 : 32,
    // Every pixel between ranks is a pixel off the zoom the whole thing gets
    // fitted to, and also the room an edge has to leave one node and arrive at
    // another without running along its edge.
    //
    // The depth is the expensive direction, and which one that is depends on the
    // rankdir: with the specialists collapsed the graph is eight ranks by two, so
    // laid out across it is 1,800px wide and 170 tall in a canvas that is now the
    // full width of the overlay. Ranks are what the fit is spent on either way.
    ranksep: across ? 36 : 28,
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

  // The router that governs each node's outgoing choice, off the compiled graph.
  // Only the deterministic three name one -- `plan` has `has_work`, `context`
  // `dispatch`, `locate` `claims`. The agent nodes fan out without one, which is
  // why the pill needs a fallback rather than a lookup that must succeed.
  const routers = new Map((shape.node_notes ?? []).map((note) => [note.node, note.router]));

  // How many ways each node can branch, so a fan can be told from a fork.
  //
  // `scout` picks any of six specialists, and six pills reading 조건 in one rank
  // is what the drawing measured as: a row of identical captions, several of
  // them landing on top of the nodes underneath. A fan that wide says "a choice
  // happens here" by being a fan. A fork of two does not, so it keeps its pill.
  const branches = new Map<string, number>();
  for (const edge of shape.edges) {
    if (edge.conditional) branches.set(edge.source, (branches.get(edge.source) ?? 0) + 1);
  }

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

  const queuedSet = new Set(queued);
  const beforeSet = new Set(before);
  const afterSet = new Set(after);

  /** Add up over the members, so the group reports the whole rank's run. */
  const sum = (of: (name: string) => number) => lenses.reduce((total, name) => total + of(name), 0);

  const nodes: Node<GraphNodeData>[] = shape.nodes.map((name) => {
    const at = graph.node(name);
    const group = name === LENS_GROUP;
    const members = group ? lenses : [];
    const mine = group ? (byNode.get(lenses[0]) ?? []) : (byNode.get(name) ?? []);
    const stat = stats?.get(name);
    // The first step's role, else the hand-written one, else the machine name --
    // which is the honest answer for a node this build has never heard of.
    const label = group ? "전문가 분석" : mine.length > 0 ? roleOf(mine[0].step) : (CODE_ROLE[name] ?? name);

    return {
      id: name,
      type: "studioNode",
      // dagre positions by centre; React Flow places by top-left corner.
      position: { x: at.x - NODE_W / 2, y: at.y - NODE_H / 2 },
      data: {
        name,
        label,
        terminal: false,
        // The group's numbers are the rank's numbers. `1×` on a node standing in
        // for five that ran twice each would be a smaller lie than no number, but
        // still a lie.
        visits: group ? sum((each) => stats?.get(each)?.visits ?? 0) : (stat?.visits ?? 0),
        averageMs: group ? null : (stat?.averageMs ?? null),
        running: group
          ? running.filter((node) => grouped.has(node)).length
          : running.filter((node) => node === name).length,
        queued: group ? lenses.some((each) => queuedSet.has(each)) : queuedSet.has(name),
        before: group ? false : beforeSet.has(name),
        after: group ? false : afterSet.has(name),
        steps: mine.map((step) => step.step),
        tools: Math.max(0, ...mine.map((step) => step.tools.length)),
        roster: steps.length > 0,
        across,
        // What the group stands for, and which of them this claim went through.
        // Named rather than counted when there is a trail to name: "이 판단은
        // memory 가 냈다" is the question the drawing is open to answer.
        members,
        litMembers: group ? litLenses.filter((each) => grouped.has(each)) : undefined,
        // `plan` could have ended the run here. Said on the node, now that the
        // `__end__` box it used to point at is not drawn.
        exits: exits.has(name),
        onInterrupt: group ? undefined : onInterrupt,
      },
      draggable: false,
      selectable: true,
    };
  });

  return {
    nodes,
    lenses,
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

      // A word on the line, where the line is. The distinction is LangGraph's own
      // -- `add_conditional_edges` against `add_edge` -- and it used to be carried
      // by a dash pattern, which means nothing until you have found and read a
      // three-item legend somewhere else on screen. Naming the router that picks
      // the edge says the same thing and says it in place; the legend is deleted.
      // A named router is always worth saying -- it is the actual condition. The
      // bare 조건 is only worth saying where it is not already obvious, which is
      // a fork rather than a fan. See `branches`.
      const label = looping
        ? "되돌아가기"
        : !e.conditional
          ? undefined
          : (routers.get(e.source) ?? ((branches.get(e.source) ?? 0) > 3 ? undefined : "조건"));

      return {
        id: edgeId(e),
        source: e.source,
        target: e.target,
        ...(side ? { sourceHandle: `${side}-out`, targetHandle: `${side}-in` } : {}),
        // Every edge is `routed`, including the loop -- which dagre never laid
        // out, so it has no points and `RoutedEdge` falls back to a step path.
        // It is one type rather than two because only the custom edge can draw
        // the label as a pill, and the loop is the one edge that most needs a
        // word on it.
        type: "routed",
        data: {
          ...(routed && routed.length > 1 ? { points: routed } : {}),
          ...(label ? { label } : {}),
          ...(looping ? { tone: "loop" as const } : e.conditional ? { tone: "conditional" as const } : {}),
          across,
        } satisfies RoutedEdgeData,
        // Only the return edge keeps an arrow. Direction is carried by rank
        // position everywhere else, and fourteen arrowheads on a drawing that
        // reads top to bottom are fourteen marks saying what the layout already
        // said. The loop is the one edge that runs against the layout.
        ...(looping ? { markerEnd: { type: MarkerType.ArrowClosed, width: 11, height: 11 } } : {}),
        className: ["gx-edge", e.conditional ? "is-conditional" : "", looping ? "is-loop" : ""]
          .filter(Boolean)
          .join(" "),
        // The loop gets a colour rather than a dash, because it is unconditional
        // too: `reduce -> plan` always runs.
        style: looping ? { stroke: "var(--alt)" } : {},
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
