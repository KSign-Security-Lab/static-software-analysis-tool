import dagre from "dagre";
import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type { GraphShape } from "@/lib/api/types";
import type { Point } from "./edge-path";
import { roleOf } from "./process";

export const NODE_W = 160;
export const NODE_H = 52;

export const TERMINALS = new Set(["__start__", "__end__"]);

export const CODE_ROLE: Record<string, string> = {
  plan: "차례 고르기",
  context: "맥락 모으기",
  skip: "건너뛰기",
  locate: "위치 찾기",
  reduce: "결과 쓰기",
};

export interface GraphNodeData extends Record<string, unknown> {
  name: string;
  label: string;
  terminal: boolean;
  visits: number;
  averageMs: number | null;
  running: number;
  queued: boolean;
  before: boolean;
  after: boolean;
  steps: string[];
  tools: number;
  faded?: boolean;
  lit?: boolean;
  roster: boolean;
  across: boolean;
  members?: string[];
  litMembers?: string[];
  exits?: boolean;
  onInterrupt?: (node: string, when: "before" | "after") => void;
}

export interface NodeStats {
  visits: number;
  averageMs: number | null;
}

export interface RoutedEdgeData extends Record<string, unknown> {
  points?: Point[];
  label?: string;
  tone?: "conditional" | "loop";
  across?: boolean;
  lit?: boolean;
}

export interface LaidOutGraph {
  nodes: Node<GraphNodeData>[];
  edges: Edge[];
  width: number;
  height: number;
  lenses: string[];
}

export const LENS_GROUP = "lens:*";

export function lensesOf(shape: GraphShape): string[] {
  const found = new Set(
    (shape.steps ?? []).filter((step) => step.step.startsWith("lens:")).map((step) => step.node),
  );
  return shape.nodes.filter((name) => found.has(name));
}

function narrow(shape: GraphShape, expanded: boolean): { shape: GraphShape; lenses: string[]; exits: Set<string> } {
  const lenses = lensesOf(shape);
  const grouped = !expanded && lenses.length > 1;
  const inGroup = new Set(grouped ? lenses : []);

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
    .filter((edge) => {
      if (edge.source === edge.target) return false;
      const id = `${edge.source}->${edge.target}`;
      if (seen.has(id)) return false;
      seen.add(id);
      return true;
    });

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
    direction?: "LR" | "TB";
    expanded?: boolean;
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
    ranksep: across ? 36 : 28,
    marginx: 28,
    marginy: 24,
  });

  const steps = shape.steps ?? [];
  const byNode = new Map<string, typeof steps>();
  for (const step of steps) byNode.set(step.node, [...(byNode.get(step.node) ?? []), step]);

  const routers = new Map((shape.node_notes ?? []).map((note) => [note.node, note.router]));

  const branches = new Map<string, number>();
  for (const edge of shape.edges) {
    if (edge.conditional) branches.set(edge.source, (branches.get(edge.source) ?? 0) + 1);
  }

  const present = new Set(shape.nodes);
  shape.nodes.forEach((name) => graph.setNode(name, { width: NODE_W, height: NODE_H }));

  const edges = shape.edges.filter((e) => present.has(e.source) && present.has(e.target));
  const back = backEdges(shape);
  const forward = edges.filter((e) => !back.has(edgeId(e)));

  forward.forEach((e) => graph.setEdge(e.source, e.target));

  const end = shape.nodes.find((n) => n === "__end__");
  if (end) {
    for (const name of sinks(shape.nodes, forward, end)) graph.setEdge(name, end);
  }

  dagre.layout(graph);

  const queuedSet = new Set(queued);
  const beforeSet = new Set(before);
  const afterSet = new Set(after);

  const sum = (of: (name: string) => number) => lenses.reduce((total, name) => total + of(name), 0);

  const nodes: Node<GraphNodeData>[] = shape.nodes.map((name) => {
    const at = graph.node(name);
    const group = name === LENS_GROUP;
    const members = group ? lenses : [];
    const mine = group ? (byNode.get(lenses[0]) ?? []) : (byNode.get(name) ?? []);
    const stat = stats?.get(name);
    const label = group ? "전문가 분석" : mine.length > 0 ? roleOf(mine[0].step) : (CODE_ROLE[name] ?? name);

    return {
      id: name,
      type: "studioNode",
      position: { x: at.x - NODE_W / 2, y: at.y - NODE_H / 2 },
      data: {
        name,
        label,
        terminal: false,
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
        members,
        litMembers: group ? litLenses.filter((each) => grouped.has(each)) : undefined,
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
      const routed = looping ? undefined : (graph.edge(e.source, e.target)?.points as Point[] | undefined);

      const side = looping ? (across ? "bottom" : "right") : null;

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
        type: "routed",
        data: {
          ...(routed && routed.length > 1 ? { points: routed } : {}),
          ...(label ? { label } : {}),
          ...(looping ? { tone: "loop" as const } : e.conditional ? { tone: "conditional" as const } : {}),
          across,
        } satisfies RoutedEdgeData,
        ...(looping ? { markerEnd: { type: MarkerType.ArrowClosed, width: 11, height: 11 } } : {}),
        className: ["gx-edge", e.conditional ? "is-conditional" : "", looping ? "is-loop" : ""]
          .filter(Boolean)
          .join(" "),
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

  const entry = shape.nodes.includes("__start__") ? ["__start__", ...shape.nodes] : shape.nodes;
  for (const name of entry) if (!state.has(name)) visit(name);
  return back;
}

function sinks(nodes: string[], forward: { source: string }[], end: string): string[] {
  const hasNext = new Set(forward.map((e) => e.source));
  return nodes.filter((name) => name !== end && !TERMINALS.has(name) && !hasNext.has(name));
}

export function statsFromSpans(spans: { name: string; kind: string; latency_ms: number | null }[]): Map<string, NodeStats> {
  const totals = new Map<string, { visits: number; ms: number; timed: number }>();

  for (const span of spans) {
    if (span.kind !== "chain") continue;
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
