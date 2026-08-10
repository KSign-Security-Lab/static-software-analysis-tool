"use client";

import { useVirtualizer } from "@tanstack/react-virtual";
import { useMemo, useRef } from "react";

import type { TraceSpan } from "@/lib/api/types";
import { place, timeline } from "@/lib/trace/gantt";
import { order, scopeTo, seconds } from "@/lib/trace/tree";
import { cn } from "@/lib/utils";

/**
 * How the agent got to its answer, as a tree of calls.
 *
 * The spine of the view. Everything the run did is here in order -- which node
 * ran, which model calls it made, which tools those reached for -- with a bar
 * per row so where the time went is visible without reading a number.
 *
 * Virtualized, and this is the one place in the app that genuinely needs it:
 * a chunk yields roughly ten spans, so a forty-chunk run is several hundred
 * fixed-height rows, and the list *grows while the run goes*, re-rendering on
 * every invalidation.
 */

const ROW = 28;

const KIND_TONE: Record<string, string> = {
  llm: "text-accent-ink",
  tool: "text-alt",
  chain: "text-ink-faint",
};

const BAR_TONE: Record<string, string> = {
  llm: "bg-accent",
  tool: "bg-alt",
  chain: "bg-line-3",
};

export default function SpanTree({
  spans,
  selected,
  node,
  waiting,
  onSelect,
}: {
  spans: TraceSpan[];
  selected: string | null;
  node: string | null;
  /** A run is in flight but has not recorded its first call yet. */
  waiting?: boolean;
  onSelect: (spanId: string) => void;
}) {
  const scroller = useRef<HTMLDivElement>(null);

  const rows = useMemo(() => order(spans), [spans]);
  // One scale for the whole trace, and a real one: each bar starts where the
  // call started and is as wide as it lasted. Four bars beginning together is
  // a wave of specialists; four in a row is one after another. A list of
  // durations cannot tell those apart.
  const scale = useMemo(() => timeline(spans), [spans]);
  const shown = useMemo(() => (node ? scopeTo(rows, node) : rows), [rows, node]);

  // The React Compiler declines to memoise this component, because
  // `useVirtualizer` returns functions it cannot prove stable. That is upstream
  // and expected; the rows below are cheap and the virtualizer already only
  // renders a windowful.
  const virtualizer = useVirtualizer({
    count: shown.length,
    getScrollElement: () => scroller.current,
    estimateSize: () => ROW,
    overscan: 12,
  });

  if (shown.length === 0) {
    // A call is recorded when it *finishes*, so a run whose first model call
    // is still thinking has nothing here yet. Telling someone to run an
    // inspection at that moment -- seconds after they pressed the button, and
    // now landed on this surface to watch it -- reads as though it never
    // started.
    return (
      <p className="p-4 text-xs text-ink-faint">
        {node
          ? `${node}에 기록된 호출이 없습니다.`
          : waiting
            ? "검사를 시작했습니다. 첫 모델 호출이 끝나는 대로 여기에 쌓입니다."
            : "기록된 호출이 없습니다. 검사를 실행하면 모델 호출과 도구 호출이 여기에 쌓입니다."}
      </p>
    );
  }

  return (
    <div ref={scroller} className="h-full overflow-auto">
      <div style={{ height: virtualizer.getTotalSize() }} className="relative">
        {virtualizer.getVirtualItems().map((item) => {
          const { span, depth } = shown[item.index];
          const { offset, width } = place(span, scale);
          return (
            <button
              key={span.id}
              type="button"
              onClick={() => onSelect(span.id)}
              style={{ height: ROW, transform: `translateY(${item.start}px)` }}
              className={cn(
                "absolute inset-x-0 top-0 flex items-center gap-2 px-2.5 text-left text-2xs transition-colors",
                "hover:bg-surface-2",
                span.id === selected && "bg-accent-wash",
                span.status === "error" && "text-danger",
              )}
            >
              <span className="flex min-w-0 shrink-0 items-center gap-1.5" style={{ paddingInlineStart: depth * 12, width: 260 }}>
                <span className={cn("shrink-0 font-mono", KIND_TONE[span.kind] ?? "text-ink-faint")}>{span.kind}</span>
                <span className="truncate text-ink">{span.name}</span>
              </span>

              <span className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3" aria-hidden>
                <span
                  className={cn("absolute inset-y-0 rounded-full", BAR_TONE[span.kind] ?? "bg-line-3")}
                  style={{ marginInlineStart: `${offset * 100}%`, width: `${width * 100}%` }}
                />
              </span>

              <span className="w-12 shrink-0 text-right font-mono text-ink-faint">{span.tokens ?? ""}</span>
              <span className="w-14 shrink-0 text-right font-mono text-ink-muted">
                {span.status === "running" ? "…" : seconds(span.latency_ms)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
