import type { TraceSpan } from "@/lib/api/types";

/**
 * Where each call sits on the wall clock.
 *
 * A bar whose width is its duration says how long something took. It cannot say
 * whether four specialists ran together or one after another, and since the run
 * became parallel that is the more interesting question -- an inspection that
 * fans out and an inspection that does not look identical as a list of
 * durations. Offsetting each bar by when it started makes overlap something you
 * can see rather than something you have to be told.
 */

export interface Placed {
  /** Fraction of the run elapsed when this started, 0-1. */
  offset: number;
  /** Fraction of the run this occupied, 0-1. */
  width: number;
}

/** Narrow enough to read as an instant, wide enough to still be a mark. */
const MIN_WIDTH = 0.004;

export function timeline(spans: TraceSpan[]): { start: number; span: number } {
  const starts = spans.map((s) => s.started_at).filter((t) => Number.isFinite(t) && t > 0);
  if (starts.length === 0) return { start: 0, span: 1 };

  const start = Math.min(...starts);
  const end = Math.max(...spans.map((s) => (s.started_at ?? start) + (s.latency_ms ?? 0) / 1000));
  // A run with one instantaneous call would otherwise divide by zero and put
  // every bar at NaN%.
  return { start, span: Math.max(end - start, 0.001) };
}

export function place(span: TraceSpan, scale: { start: number; span: number }): Placed {
  const started = Number.isFinite(span.started_at) && span.started_at > 0 ? span.started_at : scale.start;
  const offset = Math.min(1, Math.max(0, (started - scale.start) / scale.span));
  const width = Math.max(MIN_WIDTH, Math.min(1 - offset, (span.latency_ms ?? 0) / 1000 / scale.span));
  return { offset, width };
}
