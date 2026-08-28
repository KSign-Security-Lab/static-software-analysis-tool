import { describe, expect, it } from "vitest";

import type { RunStatus, RunSummary } from "@/lib/api/types";
import { IDLE, type RunLive } from "@/lib/run/reduce";
import { isScanning, phaseOf, progressOf, stageOf } from "./stage";

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
  it("has no separate screen for a run in flight", () => {
    // The findings stream in during a scan, so the results page is where the
    // scan belongs -- a third screen only cost the reader their scroll and
    // filters when it swapped at the end.
    expect(stageOf({ run: run("inspecting"), live: live(), hasFindings: false })).toBe("results");
  });

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



  it("believes the stream over the row while the stream is open", () => {
    // The row still says `indexed` for a run this tab has only just started.
    expect(stageOf({ run: run("indexed"), live: live({ active: true }), hasFindings: false })).toBe("results");
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

  it("shows a parked or stopped run, found anything or not", () => {
    // Both are "stopped, not finished", and both have a report to render even
    // when it is empty -- which is a statement about coverage, not a blank page.
    for (const status of ["interrupted", "cancelled"] as const) {
      expect(stageOf({ run: run(status), live: live(), hasFindings: true })).toBe("results");
      expect(stageOf({ run: run(status), live: live(), hasFindings: false })).toBe("results");
    }
  });

  it("keeps a failed run's findings readable, and sends an empty failure back to intake", () => {
    expect(stageOf({ run: run("failed"), live: live(), hasFindings: true })).toBe("results");
    expect(stageOf({ run: run("failed"), live: live(), hasFindings: false })).toBe("intake");
  });
});

describe("isScanning", () => {
  it("is true from the stream before the row has caught up", () => {
    expect(isScanning({ run: run("indexed"), live: live({ active: true }) })).toBe(true);
  });

  it("is true from the row before the stream has attached", () => {
    // A tab that arrives mid-run has a row saying `inspecting` and no
    // EventSource yet; the strip has to appear anyway.
    expect(isScanning({ run: run("inspecting"), live: live() })).toBe(true);
  });

  it("is false once the stream says it finished", () => {
    expect(isScanning({ run: run("done"), live: live({ active: true, finished: true }) })).toBe(false);
  });

  it("is false with no run at all", () => {
    expect(isScanning({ run: undefined, live: live() })).toBe(false);
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
