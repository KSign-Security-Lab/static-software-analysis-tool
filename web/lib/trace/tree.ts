import type { TraceSpan } from "@/lib/api/types";

/**
 * The call tree, as rows.
 *
 * Extracted out of the component so it stays testable without a DOM -- the
 * ordering invariant below is subtle enough to be worth covering directly, and
 * `scopeTo` silently depends on it.
 */

export interface Row {
  span: TraceSpan;
  depth: number;
}

/**
 * Parent before child, each child under its own parent.
 *
 * The store returns spans in the order they opened, which interleaves siblings
 * once anything runs nested. Walking the parent links puts each call under the
 * one that made it.
 */
export function order(spans: TraceSpan[]): Row[] {
  const children = new Map<string, TraceSpan[]>();
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

/**
 * Only the calls belonging to one node of the graph.
 *
 * A whole subtree, not just the rows whose name matches: a node's model calls
 * and the tools those reached for are what "what did verify do" means. Depth is
 * re-based so the kept rows start at the left instead of being indented by
 * however deep they happened to sit.
 *
 * Relies on `order` emitting each subtree contiguously, which a depth-first
 * walk does. Changing that walk breaks this silently.
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

/** `1.42s` / `840ms`, or nothing for a call still running. */
export function seconds(ms: number | null): string {
  if (ms === null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`;
}
