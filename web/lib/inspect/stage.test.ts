import { describe, expect, it } from "vitest";

import type { RunStatus, RunSummary } from "@/lib/api/types";
import { IDLE, type RunLive } from "@/lib/run/reduce";
import { phaseOf, progressOf, stageOf } from "./stage";

function run(status: RunStatus): RunSummary {
  return {
    run_id: "r1",
    status,
    files: ["app.c"],
    file_count: 1,
    updated_at: 0,
    started: false,
  };
}

function live(over: Partial<RunLive> = {}): RunLive {
  return { ...IDLE, ...over };
}

describe("stageOf", () => {
  it("shows intake when there is no run", () => {
    expect(stageOf({ run: undefined, live: live(), hasFindings: false })).toBe("intake");
  });

  it("keeps intake while the upload is still being read", () => {
    // Intake is the screen with somewhere to put "reading 1,204 files".
    expect(stageOf({ run: run("created"), live: live(), hasFindings: false })).toBe("intake");
    expect(stageOf({ run: run("indexing"), live: live(), hasFindings: false })).toBe("intake");
  });

  it("keeps intake for an indexed run nobody has started", () => {
    expect(stageOf({ run: run("indexed"), live: live(), hasFindings: false })).toBe("intake");
  });

  it("shows scanning while the run is inspecting", () => {
    expect(stageOf({ run: run("inspecting"), live: live(), hasFindings: false })).toBe("scanning");
  });

  it("believes the stream over the row while the stream is open", () => {
    // `run_finished` arrives before the status column is re-read, and the row
    // still says `indexed` for a run this tab has only just started.
    expect(stageOf({ run: run("indexed"), live: live({ active: true }), hasFindings: false })).toBe("scanning");
  });

  it("goes to results once the stream says the run finished", () => {
    // Active *and* finished: the EventSource is still attached but the work is
    // done, which used to read as still scanning.
    const stream = live({ active: true, finished: true });
    expect(stageOf({ run: run("done"), live: stream, hasFindings: true })).toBe("results");
  });

  it("shows results for a finished run", () => {
    expect(stageOf({ run: run("done"), live: live(), hasFindings: true })).toBe("results");
    // A clean report is still a result. "Nothing found" is an answer.
    expect(stageOf({ run: run("done"), live: live(), hasFindings: false })).toBe("results");
  });

  it("shows what a parked run has already found rather than a third progress screen", () => {
    expect(stageOf({ run: run("interrupted"), live: live(), hasFindings: true })).toBe("results");
    expect(stageOf({ run: run("interrupted"), live: live(), hasFindings: false })).toBe("scanning");
  });

  it("keeps a failed run's findings readable, and sends an empty failure back to intake", () => {
    expect(stageOf({ run: run("failed"), live: live(), hasFindings: true })).toBe("results");
    expect(stageOf({ run: run("failed"), live: live(), hasFindings: false })).toBe("intake");
  });
});

describe("phaseOf", () => {
  it("says nothing when nothing is running", () => {
    expect(phaseOf(live())).toBeNull();
    expect(phaseOf(live({ active: true, finished: true }))).toBeNull();
  });

  it("reports being parked before anything else", () => {
    expect(phaseOf(live({ active: true, interrupted: true, running: ["verify"] }))).toBe("중단점에서 멈춤");
  });

  it("picks the furthest-along node when several run at once", () => {
    // A wave screens in parallel, so `running` is genuinely a list. Reporting
    // the latest stage reads better than reporting whichever arrived last.
    expect(phaseOf(live({ active: true, running: ["triage", "verify", "memory"] }))).toBe("반박해 보는 중");
  });

  it("translates a node nobody outside the graph would recognise", () => {
    expect(phaseOf(live({ active: true, running: ["triage"] }))).toBe("볼 만한 단위인지 가리는 중");
  });

  it("says something rather than nothing for a node it has no phrase for", () => {
    expect(phaseOf(live({ active: true, running: ["something_new"] }))).toBe("준비 중");
    expect(phaseOf(live({ active: true, running: [] }))).toBe("준비 중");
  });
});

describe("progressOf", () => {
  it("has no fraction before the total is known", () => {
    expect(progressOf(live())).toEqual({ done: 0, total: 0, fraction: null });
  });

  it("counts done as total minus remaining", () => {
    const at = live({ chunk: { id: "c", remaining: 3, total: 10 } });
    expect(progressOf(at)).toEqual({ done: 7, total: 10, fraction: 0.7 });
  });

  it("never reports more than done", () => {
    // `remaining` is the queue and can lag the total by a frame.
    const at = live({ chunk: { id: "c", remaining: 0, total: 4 } });
    expect(progressOf(at).fraction).toBe(1);
    const odd = live({ chunk: { id: "c", remaining: 9, total: 4 } });
    expect(odd.chunk && progressOf(odd).done).toBe(0);
  });
});
