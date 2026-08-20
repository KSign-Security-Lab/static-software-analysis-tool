import type { TraceSpan } from "@/lib/api/types";
import type { RunLive } from "@/lib/run/reduce";
import { CODE_ROLE } from "@/lib/trace/layout";
import { roleOf } from "@/lib/trace/process";

/**
 * What the run is doing right now, in the reader's language.
 *
 * A scan is minutes of nothing visible, and "검사 중" for four minutes is
 * indistinguishable from a hang. Everything below is already on the wire -- the
 * stream names the nodes executing and the units they hold, and the span table
 * records every tool call -- it simply had nowhere to be shown.
 *
 * Labels are borrowed, not coined. `CODE_ROLE` names the five deterministic
 * nodes and `roleOf` narrates the agent steps; both already appear on the
 * structure drawing and in a finding's 판단 과정, so a reader who learns a name
 * here recognises it there.
 */

/** The five specialists, which are nodes here and `lens:` steps everywhere else. */
export const LENSES = ["memory", "injection", "access", "crypto", "logic"] as const;

export function nodeLabel(node: string): string {
  if (CODE_ROLE[node]) return CODE_ROLE[node];
  // `roleOf` speaks step ids, and a lens is `lens:memory` there but `memory`
  // as a graph node. Prefixing is cheaper than a second table that can drift.
  if ((LENSES as readonly string[]).includes(node)) return roleOf(`lens:${node}`);
  return roleOf(node);
}

export interface Agent {
  node: string;
  label: string;
  /** A specialist reads one unit at a time; the deterministic nodes do not. */
  lens: boolean;
  /**
   * How many copies of this node are executing.
   *
   * Genuinely more than one: the graph fans out with `Send`, so a wave puts
   * several units through `skip` or `gather` at the same instant. Rendered as a
   * count rather than as repeated rows -- two identical lines reading
   * `건너뛰기 skip` look like a rendering fault, and keying a list by node name
   * when the name repeats is one (it was: React reported duplicate keys).
   */
  count: number;
}

/**
 * The nodes executing, worst-jargon-first translated.
 *
 * Genuinely several at once: a wave screens in parallel and the five specialists
 * are dispatched together, which is why `RunLive.running` is a list and why one
 * name here would have shown whichever event arrived last.
 */
export function activeAgents(live: RunLive): Agent[] {
  const counts = new Map<string, number>();
  for (const node of live.running) counts.set(node, (counts.get(node) ?? 0) + 1);
  return [...counts.entries()].map(([node, count]) => ({
    node,
    label: nodeLabel(node),
    lens: (LENSES as readonly string[]).includes(node),
    count,
  }));
}

/**
 * Files with a unit currently being read, each once.
 *
 * `inflight` is keyed by unit rather than by file because a wave is often two
 * functions of the same file -- collected into a set, the file would read as
 * being worked on long after both were done.
 */
export function filesInFlight(live: RunLive): string[] {
  return [...new Set(live.inflight.values())].sort();
}

/**
 * Files a unit of which has already come back, most recent first.
 *
 * The fallback for the ordinary case that `inflight` is empty: the stream cannot
 * be replayed, so a tab opened part-way through a scan missed every
 * `chunk_started` before it attached and knows only what has *finished* since.
 * Showing nothing there would read as nothing happening, which is exactly the
 * impression this panel exists to correct.
 *
 * A `Set` keeps insertion order, so reversing it is newest-first.
 */
export function filesScanned(live: RunLive): string[] {
  return [...live.scanned].reverse();
}

export interface ToolCall {
  id: string;
  name: string;
  /** What it was called about, when the span name carries it. */
  subject: string;
  running: boolean;
  failed: boolean;
  latencyMs: number | null;
}

/**
 * The most recent tool calls, newest first.
 *
 * From the span table rather than the stream: the stream carries node
 * transitions and findings, not tool calls, and the spans are invalidated on
 * every node event anyway -- so this refreshes as the run moves without a poll
 * of its own.
 */
export function recentTools(spans: TraceSpan[], limit = 8): ToolCall[] {
  return spans
    .filter((span) => span.kind === "tool")
    .sort((a, b) => b.seq - a.seq)
    .slice(0, limit)
    .map((span) => {
      const at = span.name.indexOf(":");
      return {
        id: span.id,
        name: at === -1 ? span.name : span.name.slice(0, at),
        subject: at === -1 ? "" : span.name.slice(at + 1),
        running: span.status === "running",
        failed: span.status === "error",
        latencyMs: span.latency_ms,
      };
    });
}
