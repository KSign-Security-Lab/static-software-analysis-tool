"use client";

import { useMemo } from "react";

import type { GraphShape, Span } from "@/lib/api/agent";

/**
 * The agent's structure: the nodes it can be in and the edges between them,
 * with what actually happened on this run laid over the top.
 *
 * Drawn here rather than with a diagram library. The graph is a handful of
 * nodes and one loop, and a layered layout of that is less code than the
 * dependency would be -- and it can carry per-node run counts, which a static
 * mermaid render cannot.
 */

const ROW = 62;
const NODE_W = 150;
const NODE_H = 34;
const PAD = 20;
const GUTTER = 74; // room on the right for the loop-back arc

interface NodeStat {
  runs: number;
  ms: number;
  running: boolean;
}

/** Longest-path depth, ignoring back edges so the loop does not stretch it. */
function levels(shape: GraphShape): Map<string, number> {
  const back = backEdges(shape);
  const incoming = new Map<string, string[]>();
  for (const node of shape.nodes) incoming.set(node, []);
  for (const edge of shape.edges) {
    if (back.has(`${edge.source}->${edge.target}`)) continue;
    incoming.get(edge.target)?.push(edge.source);
  }

  const depth = new Map<string, number>();
  const of = (node: string, guard = 0): number => {
    const known = depth.get(node);
    if (known !== undefined) return known;
    if (guard > shape.nodes.length) return 0;
    depth.set(node, 0);
    const parents = incoming.get(node) ?? [];
    const value = parents.length ? Math.max(...parents.map((p) => of(p, guard + 1) + 1)) : 0;
    depth.set(node, value);
    return value;
  };
  shape.nodes.forEach((n) => of(n));

  // A terminal sink belongs at the bottom, not beside whichever node happens
  // to branch into it -- `plan -> __end__` would otherwise put it at row 2.
  const deepest = Math.max(...depth.values());
  for (const node of shape.nodes) {
    if (!shape.edges.some((e) => e.source === node)) depth.set(node, deepest + 1);
  }
  return depth;
}

/** Edges that close a cycle, found by DFS from the entry node. */
function backEdges(shape: GraphShape): Set<string> {
  const out = new Map<string, string[]>();
  for (const edge of shape.edges) out.set(edge.source, [...(out.get(edge.source) ?? []), edge.target]);

  const found = new Set<string>();
  const state = new Map<string, 0 | 1 | 2>();
  const walk = (node: string) => {
    state.set(node, 1);
    for (const next of out.get(node) ?? []) {
      const seen = state.get(next);
      if (seen === 1) found.add(`${node}->${next}`);
      else if (seen === undefined) walk(next);
    }
    state.set(node, 2);
  };
  shape.nodes.forEach((n) => state.get(n) === undefined && walk(n));
  return found;
}

/** How often each node ran on this trace, and how long it spent. */
function statsFrom(spans: Span[]): Map<string, NodeStat> {
  const out = new Map<string, NodeStat>();
  for (const span of spans) {
    if (span.kind !== "chain") continue;
    const stat = out.get(span.name) ?? { runs: 0, ms: 0, running: false };
    stat.runs += 1;
    stat.ms += span.latency_ms ?? 0;
    if (span.status === "running") stat.running = true;
    out.set(span.name, stat);
  }
  return out;
}

function label(node: string): string {
  return node === "__start__" ? "시작" : node === "__end__" ? "종료" : node;
}

export default function GraphView({ shape, spans }: { shape: GraphShape; spans: Span[] }) {
  const depth = useMemo(() => levels(shape), [shape]);
  const back = useMemo(() => backEdges(shape), [shape]);
  const stats = useMemo(() => statsFrom(spans), [spans]);

  const rows = Math.max(...depth.values()) + 1;
  const height = rows * ROW + PAD * 2;
  const width = NODE_W + PAD * 2 + GUTTER;
  const cx = PAD + NODE_W / 2;
  const y = (node: string) => PAD + (depth.get(node) ?? 0) * ROW + NODE_H / 2;

  return (
    <div className="graphview">
      <svg width={width} height={height} className="graphview-svg" role="img" aria-label="에이전트 그래프">
        <defs>
          <marker id="gv-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--line-2)" />
          </marker>
        </defs>

        {shape.edges.map((edge) => {
          const from = y(edge.source);
          const to = y(edge.target);
          const isBack = back.has(`${edge.source}->${edge.target}`);
          // Back edges bow out to the right so they do not overdraw the
          // straight run of the main path.
          const d = isBack
            ? `M ${cx + NODE_W / 2} ${from} C ${cx + NODE_W / 2 + GUTTER} ${from}, ${cx + NODE_W / 2 + GUTTER} ${to}, ${cx + NODE_W / 2} ${to}`
            : `M ${cx} ${from + NODE_H / 2} L ${cx} ${to - NODE_H / 2}`;
          return (
            <path
              key={`${edge.source}->${edge.target}`}
              d={d}
              className={`gv-edge ${edge.conditional ? "is-conditional" : ""}`}
              markerEnd="url(#gv-arrow)"
              fill="none"
            />
          );
        })}

        {shape.nodes.map((node) => {
          const stat = stats.get(node);
          const terminal = node.startsWith("__");
          return (
            <g key={node} transform={`translate(${PAD}, ${y(node) - NODE_H / 2})`}>
              <rect
                width={NODE_W}
                height={NODE_H}
                rx={terminal ? NODE_H / 2 : 7}
                className={`gv-node ${terminal ? "is-terminal" : ""} ${stat ? "is-visited" : ""} ${stat?.running ? "is-running" : ""}`}
              />
              <text x={12} y={NODE_H / 2 + 4} className="gv-label">
                {label(node)}
              </text>
              {stat && (
                <text x={NODE_W - 12} y={NODE_H / 2 + 4} textAnchor="end" className="gv-count">
                  ×{stat.runs}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <dl className="graphview-legend">
        {shape.nodes
          .filter((node) => !node.startsWith("__"))
          .map((node) => {
            const stat = stats.get(node);
            return (
              <div key={node} className="gv-stat">
                <dt>{node}</dt>
                <dd>
                  {stat ? `${stat.runs}회 · ${(stat.ms / 1000).toFixed(2)}s` : "실행 안 됨"}
                  {stat?.running ? " · 진행 중" : ""}
                </dd>
              </div>
            );
          })}
        <div className="gv-stat">
          <dt>조건부 분기</dt>
          <dd>{shape.edges.filter((e) => e.conditional).length}개 (점선)</dd>
        </div>
      </dl>
    </div>
  );
}
