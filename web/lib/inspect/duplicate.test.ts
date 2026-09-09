import { describe, expect, it } from "vitest";

import type { RunStatus, RunSummary } from "@/lib/api/types";
import { bestMatch, duplicateOf, summarise } from "./duplicate";

function run(over: Partial<RunSummary> & { status: RunStatus }): RunSummary {
  return {
    run_id: "r1",
    files: ["app.c"],
    file_count: 1,
    updated_at: 0,
    started: true,
    ...over,
  };
}

describe("duplicateOf", () => {
  it("opens a finished run", () => {
    expect(duplicateOf(run({ status: "done" })).action).toBe("open");
  });

  it("carries on a run that stopped part-way", () => {
    expect(duplicateOf(run({ status: "failed" })).action).toBe("resume");
    expect(duplicateOf(run({ status: "cancelled" })).action).toBe("resume");
  });

  it("tells a parked run apart, because it is a different endpoint", () => {
    expect(duplicateOf(run({ status: "interrupted" })).action).toBe("unpark");
  });

  it("offers to watch a run that is already going", () => {
    expect(duplicateOf(run({ status: "inspecting" })).action).toBe("watch");
  });

  it("starts a tree that has never been scanned", () => {
    for (const status of ["created", "indexing", "indexed"] as const) {
      expect(duplicateOf(run({ status })).action).toBe("start");
    }
  });

  it("gives every action a label and a reason", () => {
    for (const status of ["done", "failed", "cancelled", "interrupted", "inspecting", "indexed"] as const) {
      const offer = duplicateOf(run({ status }));
      expect(offer.label.length).toBeGreaterThan(0);
      expect(offer.note.length).toBeGreaterThan(0);
    }
  });
});

describe("summarise", () => {
  it("says what was found only for a run that finished", () => {
    expect(summarise(run({ status: "done", findings: 3 }))).toContain("3건 발견");
    expect(summarise(run({ status: "done", findings: 0 }))).toContain("발견된 것 없음");
    expect(summarise(run({ status: "failed", findings: 0 }))).not.toContain("발견");
  });

  it("always says how much code it was", () => {
    expect(summarise(run({ status: "indexed", file_count: 12 }))).toContain("파일 12개");
  });

  it("adds the unit count when the run was indexed", () => {
    const indexed = run({
      status: "done",
      findings: 1,
      index: { files_indexed: 1, files_skipped: 0, chunks: 7, links: 3 },
    });
    expect(summarise(indexed)).toContain("단위 7개");
  });
});

describe("bestMatch", () => {
  it("prefers a finished run over a more recent unstarted one", () => {
    const chosen = bestMatch([
      run({ status: "indexed", run_id: "newer-empty", updated_at: 200 }),
      run({ status: "done", run_id: "older-done", updated_at: 100 }),
    ]);
    expect(chosen?.run_id).toBe("older-done");
  });

  it("prefers a run already going over one that must be resumed", () => {
    const chosen = bestMatch([
      run({ status: "failed", run_id: "resumable", updated_at: 200 }),
      run({ status: "inspecting", run_id: "running", updated_at: 100 }),
    ]);
    expect(chosen?.run_id).toBe("running");
  });

  it("prefers work already paid for over a bare tree", () => {
    const chosen = bestMatch([
      run({ status: "created", run_id: "bare", updated_at: 200 }),
      run({ status: "cancelled", run_id: "part-done", updated_at: 100 }),
    ]);
    expect(chosen?.run_id).toBe("part-done");
  });

  it("falls back to the newest when two are equally useful", () => {
    const chosen = bestMatch([
      run({ status: "done", run_id: "older", updated_at: 100 }),
      run({ status: "done", run_id: "newer", updated_at: 200 }),
    ]);
    expect(chosen?.run_id).toBe("newer");
  });

  it("is undefined when there is nothing to offer", () => {
    expect(bestMatch([])).toBeUndefined();
  });
});
