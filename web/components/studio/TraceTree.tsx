"use client";

import { useMemo } from "react";

import type { Span } from "@/lib/api/studio";
import { place, timeline } from "@/lib/studio/gantt";

/**
 * How the agent got to its answer, as a tree of calls.
 *
 * This is the spine of the view. Everything the run did is here in order --
 * which node ran, which model calls it made, which tools those reached for --
 * with a bar per row so where the time went is visible without reading a single
 * number. Selecting a row is what opens it for editing and re-running.
 */

function seconds(ms: number | null): string {
  if (ms === null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`;
}

function kindClass(kind: string): string {
  if (kind === "llm") return "k-llm";
  if (kind === "tool") return "k-tool";
  if (kind === "chain") return "k-chain";
  return "k-other";
}

export interface Row {
  span: Span;
  depth: number;
}

/**
 * Only the calls belonging to one node of the graph.
 *
 * A whole subtree, not just the rows whose name matches: a node's model calls
 * and the tools those reached for are what "what did verify do" means. Depth is
 * re-based so the kept rows start at the left instead of being indented by
 * however deep they happened to sit.
 *
 * Relies on :func:`order` emitting each subtree contiguously, which a
 * depth-first walk does.
 */
export function scopeTo(rows: Row[], node: string): Row[] {
  const out: Row[] = [];
  let base: number | null = null;

  for (const row of rows) {
    if (row.span.name.split(":")[0] === node) {
      base = row.depth;
      out.push({ span: row.span, depth: 0 });
    } else if (base !== null && row.depth > base) {
      out.push({ span: row.span, depth: row.depth - base });
    } else {
      // Back out to the matched node's level or above: that subtree is over.
      base = null;
    }
  }
  return out;
}

/**
 * Parent before child, each child under its own parent.
 *
 * The store returns spans in the order they opened, which interleaves siblings
 * once anything runs nested. Walking the parent links puts each call under the
 * one that made it.
 */
export function order(spans: Span[]): Row[] {
  const children = new Map<string, Span[]>();
  const known = new Set(spans.map((s) => s.id));

  for (const span of spans) {
    // A span whose parent was never written is treated as a root, so a
    // truncated trace still shows everything it does have.
    const key = span.parent_id && known.has(span.parent_id) ? span.parent_id : "";
    children.set(key, [...(children.get(key) ?? []), span]);
  }

  const rows: Row[] = [];
  const walk = (parent: string, depth: number) => {
    for (const span of children.get(parent) ?? []) {
      rows.push({ span, depth });
      walk(span.id, depth + 1);
    }
  };
  walk("", 0);
  return rows;
}

export default function TraceTree({
  spans,
  selected,
  onSelect,
  node,
}: {
  spans: Span[];
  selected: string | null;
  onSelect: (spanId: string) => void;
  node: string | null;
}) {
  const rows = useMemo(() => order(spans), [spans]);

  // One scale for the whole trace, and a real one: each bar starts where the
  // call started and is as wide as it lasted. Four bars beginning at the same
  // point is a wave of specialists; four in a row is one after another. A list
  // of durations cannot tell those apart.
  const scale = useMemo(() => timeline(spans), [spans]);

  const shown = node ? scopeTo(rows, node) : rows;

  if (shown.length === 0) {
    return (
      <p className="sx-muted sx-pad">
        {node
          ? `${node}에 기록된 호출이 없습니다.`
          : "기록된 호출이 없습니다. 검사를 실행하면 모델 호출과 도구 호출이 여기에 쌓입니다."}
      </p>
    );
  }

  return (
    <div className="tx-tree">
      {shown.map(({ span, depth }) => {
        const { offset, width } = place(span, scale);
        return (
          <button
            key={span.id}
            type="button"
            className={`tx-row ${span.id === selected ? "is-selected" : ""} ${span.status === "error" ? "is-error" : ""}`}
            onClick={() => onSelect(span.id)}
          >
            <span className="tx-name" style={{ paddingLeft: depth * 14 }}>
              <span className={`sx-kind ${kindClass(span.kind)}`}>{span.kind}</span>
              <span className="tx-label">{span.name}</span>
            </span>

            <span className="tx-bar" aria-hidden>
              <span
                className={`tx-bar-fill ${kindClass(span.kind)}`}
                style={{ marginInlineStart: `${offset * 100}%`, width: `${width * 100}%` }}
              />
            </span>

            <span className="tx-tokens">{span.tokens ? `${span.tokens}` : ""}</span>
            <span className="tx-ms">{span.status === "running" ? "…" : seconds(span.latency_ms)}</span>
          </button>
        );
      })}
    </div>
  );
}
