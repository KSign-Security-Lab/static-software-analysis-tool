import { describe, expect, it } from "vitest";

import type { Span } from "@/lib/api/studio";
import { place, timeline } from "./gantt";

function span(id: string, startedAt: number, ms: number | null): Span {
  return {
    id,
    parent_id: null,
    seq: 0,
    name: id,
    kind: "llm",
    status: ms === null ? "running" : "ok",
    error: null,
    started_at: startedAt,
    latency_ms: ms,
    tokens: null,
    meta: {},
    inputs: null,
    outputs: null,
  };
}

describe("gantt", () => {
  it("shows four specialists on one chunk as four bars at the same place", () => {
    // The whole reason for offsetting the bars. As a list of durations this and
    // the sequential case below are indistinguishable.
    const together = [span("memory", 100, 2000), span("injection", 100, 2000), span("access", 100, 2000)];
    const scale = timeline(together);
    const placed = together.map((s) => place(s, scale));

    expect(placed.every((p) => p.offset === 0)).toBe(true);
    expect(placed.every((p) => p.width === 1)).toBe(true);
  });

  it("shows the same three run one after another as a staircase", () => {
    const sequential = [span("a", 100, 1000), span("b", 101, 1000), span("c", 102, 1000)];
    const scale = timeline(sequential);
    const offsets = sequential.map((s) => place(s, scale).offset);

    expect(offsets[0]).toBe(0);
    expect(offsets[1]).toBeGreaterThan(offsets[0]);
    expect(offsets[2]).toBeGreaterThan(offsets[1]);
  });

  it("never runs a bar past the end of the trace", () => {
    const spans = [span("a", 100, 1000), span("b", 100, 60_000)];
    const scale = timeline(spans);
    for (const s of spans) {
      const { offset, width } = place(s, scale);
      expect(offset + width).toBeLessThanOrEqual(1.0001);
    }
  });

  it("still draws a mark for something instantaneous", () => {
    const spans = [span("blink", 100, 0), span("long", 100, 10_000)];
    const scale = timeline(spans);
    expect(place(spans[0], scale).width).toBeGreaterThan(0);
  });

  it("survives a trace with nothing in it, and one still running", () => {
    expect(timeline([])).toEqual({ start: 0, span: 1 });

    const live = [span("open", 100, null)];
    const { offset, width } = place(live[0], timeline(live));
    expect(Number.isFinite(offset) && Number.isFinite(width)).toBe(true);
  });
});
