import type { TraceSpan } from "@/lib/api/types";
import type { RunLive } from "@/lib/run/reduce";
import { CODE_ROLE } from "@/lib/trace/layout";
import { roleOf } from "@/lib/trace/process";

export const LENSES = ["memory", "injection", "access", "crypto", "logic"] as const;

export function nodeLabel(node: string): string {
  if (CODE_ROLE[node]) return CODE_ROLE[node];
  if ((LENSES as readonly string[]).includes(node)) return roleOf(`lens:${node}`);
  return roleOf(node);
}

export interface Agent {
  node: string;
  label: string;
  lens: boolean;
  count: number;
}

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

export function filesInFlight(live: RunLive): string[] {
  return [...new Set(live.inflight.values())].sort();
}

export function filesScanned(live: RunLive): string[] {
  return [...live.scanned].reverse();
}

export interface ToolCall {
  id: string;
  name: string;
  subject: string;
  running: boolean;
  failed: boolean;
  latencyMs: number | null;
}

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
