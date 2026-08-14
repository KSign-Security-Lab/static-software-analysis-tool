"use client";

import { useEffect, useMemo, useRef } from "react";

import { PanelShell } from "@/components/workbench/PanelShell";
import type { TraceSpan } from "@/lib/api/types";
import { phaseFor } from "@/lib/run/reduce";
import { useRun } from "@/lib/run/queries";
import { idOf, useSelection } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * Everything the run did, in the order it did it.
 *
 * The trace has always been here -- `useSpans` feeds the node counts on the
 * drawing and the cost row on the run bar -- but the only way to read a single
 * call was to find the row that raised a finding and open it. A run is a
 * sequence and nothing showed it as one.
 *
 * A log rather than a tree: the spans nest four deep and the shape of the
 * nesting is the graph, which is drawn above this. What a flat list adds is
 * *when*, which the drawing cannot show at all -- six specialists that look
 * simultaneous on the canvas went in some order, and that order is often the
 * answer to why one of them saw something the others did not.
 *
 * Clicking a line selects the call, and the rail beside it fills with the
 * prompts, the reply and the tool results. Same rule as the rest of the surface:
 * something picks, the inspector details.
 */
export default function RunLog() {
  const [runId] = useRunId();
  const spans = useSpans(runId);
  const run = useRun(runId);
  const { live, phase: streamed } = useRunStream();
  const { selection, select } = useSelection();
  const open = idOf(selection, "call");

  const phase = phaseFor(streamed, run.data?.status);
  const busy = phase === "running" || phase === "starting";

  // In the order the server assigned, not the order they finished. `seq` is the
  // trace's own sequence and it is what makes a wave's six lenses readable as
  // six things rather than as whatever order six responses happened to land in.
  const rows = useMemo(() => {
    const all = spans.data?.spans ?? [];
    return [...all].sort((a, b) => a.seq - b.seq);
  }, [spans.data]);

  const foot = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    // Only while it is moving. Yanking somebody to the bottom of a finished log
    // they were reading the middle of is the behaviour every console gets wrong.
    if (busy) foot.current?.scrollIntoView({ block: "end" });
  }, [rows.length, busy]);

  return (
    <PanelShell
      title="실행 기록"
      note={
        <span className={cn("text-2xs", busy ? "text-accent-ink" : "text-ink-faint")}>
          {busy ? `진행 중 · ${rows.length}` : rows.length > 0 ? `${rows.length}건` : ""}
        </span>
      }
      bodyClassName="overflow-hidden"
    >
      {rows.length === 0 ? (
        <p className="px-3 py-3 text-2xs text-ink-faint">
          {busy ? "첫 호출을 기다리는 중입니다." : "이 검사에는 기록이 없습니다. ‘검사 실행’을 누르세요."}
        </p>
      ) : (
        // A plain scrolling div rather than `ScrollArea`, for the reason
        // NodeRoster spells out: Radix's viewport sizes to content, and a span
        // named `verify:CWE-122 src/g.c:6` is wider than this panel.
        <div className="h-full min-w-0 overflow-auto">
          <ul className="min-w-0 py-1">
            {rows.map((span) => (
              <Line key={span.id} span={span} open={span.id === open} onPick={() => select({ kind: "call", id: span.id })} />
            ))}
          </ul>
          <div ref={foot} />
        </div>
      )}

      {live.error && <p className="border-t border-line px-3 py-1 text-2xs text-danger">{live.error}</p>}
    </PanelShell>
  );
}

/** `14:44:29.920  gather:a1b2  2 calls · 3,930 tok · 2.7s` */
function Line({ span, open, onPick }: { span: TraceSpan; open: boolean; onPick: () => void }) {
  const at = new Date(span.started_at * 1000);
  const clock = `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}:${String(
    at.getSeconds(),
  ).padStart(2, "0")}.${String(at.getMilliseconds()).padStart(3, "0")}`;

  const running = span.status === "running";
  const failed = span.status === "error" || Boolean(span.error);

  return (
    <li>
      <button
        type="button"
        onClick={onPick}
        className={cn(
          "flex w-full items-baseline gap-2 px-3 py-0.5 text-left font-mono text-2xs hover:bg-surface-2",
          open && "bg-accent-wash",
        )}
      >
        <span className="shrink-0 text-ink-faint/70">{clock}</span>
        {/* The kinds read very differently and the eye should be able to skip
            two of them: `chain` is a node entering, `tool` is a lookup, and
            `llm` is the one that cost money and took a second. */}
        <span
          className={cn(
            "w-9 shrink-0",
            span.kind === "llm" ? "text-accent-ink" : span.kind === "tool" ? "text-alt" : "text-ink-faint",
          )}
        >
          {span.kind}
        </span>
        <span className={cn("min-w-0 flex-1 truncate", failed ? "text-danger" : open ? "text-ink-strong" : "text-ink")}>
          {span.name}
        </span>
        {span.tokens ? <span className="shrink-0 text-ink-faint">{span.tokens.toLocaleString()} tok</span> : null}
        <span className="w-12 shrink-0 text-right text-ink-faint">
          {running ? "…" : span.latency_ms === null ? "" : span.latency_ms < 1000 ? `${span.latency_ms}ms` : `${(span.latency_ms / 1000).toFixed(1)}s`}
        </span>
      </button>
    </li>
  );
}
