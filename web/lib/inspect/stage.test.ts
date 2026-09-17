import { describe, expect, it } from "vitest";

import type { RunStatus, RunSummary } from "@/lib/api/types";
import { IDLE, type RunLive } from "@/lib/run/reduce";
import { isScanning, isStopped, phaseOf, progressOf, stageOf } from "./stage";

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
    expect(stageOf({ run: run("inspecting"), live: live(), hasFindings: false })).toBe("results");
  });

  it("shows intake when there is no run", () => {
    expect(stageOf({ run: undefined, live: live(), hasFindings: false })).toBe("intake");
  });

  it("keeps intake while the upload is still being read", () => {
    expect(stageOf({ run: run("created"), live: live(), hasFindings: false })).toBe("intake");
    expect(stageOf({ run: run("indexing"), live: live(), hasFindings: false })).toBe("intake");
  });

  it("keeps intake for an indexed run nobody has started", () => {
    expect(stageOf({ run: run("indexed"), live: live(), hasFindings: false })).toBe("intake");
  });

  it("believes the stream over the row while the stream is open", () => {
    expect(stageOf({ run: run("indexed"), live: live({ active: true }), hasFindings: false })).toBe("results");
  });

  it("goes to results once the stream says the run finished", () => {
    const stream = live({ active: true, finished: true });
    expect(stageOf({ run: run("done"), live: stream, hasFindings: true })).toBe("results");
  });

  it("shows results for a finished run", () => {
    expect(stageOf({ run: run("done"), live: live(), hasFindings: true })).toBe("results");
    expect(stageOf({ run: run("done"), live: live(), hasFindings: false })).toBe("results");
  });

  it("shows a parked or stopped run, found anything or not", () => {
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
    expect(isScanning({ run: run("indexed"), live: live({ active: true, attached: true }) })).toBe(true);
  });

  it("stops believing a detached stream once the row says the run is over", () => {
    expect(isScanning({ run: run("done"), live: live({ active: true }) })).toBe(false);
    expect(isScanning({ run: run("cancelled"), live: live({ active: true }) })).toBe(false);
  });

  it("is true from the row before the stream has attached", () => {
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
    const at = live({ chunk: { id: "c", remaining: 0, total: 4 } });
    expect(progressOf(at).fraction).toBe(1);
    const odd = live({ chunk: { id: "c", remaining: 9, total: 4 } });
    expect(odd.chunk && progressOf(odd).done).toBe(0);
  });
});

describe("a scan that has been told to stop", () => {
  it("says so, ahead of whichever specialist it is inside", () => {
    expect(phaseOf(live({ active: true, running: ["injection"], cancelling: true }))).toBe("중단하는 중");
  });

  it("does not offer the breakpoint wording instead", () => {
    expect(phaseOf(live({ active: true, interrupted: true, cancelling: true }))).toBe("중단하는 중");
  });

  it("keeps reading as scanning until something confirms it ended", () => {
    expect(isScanning({ run: run("inspecting"), live: live({ active: true, cancelling: true }) })).toBe(true);
  });

  it("stops when the row says it stopped, even if the stream never said so", () => {
    expect(isScanning({ run: run("cancelled"), live: live({ active: true, cancelling: true }) })).toBe(false);
  });

  it("still trusts the stream when no stop is outstanding and it is attached", () => {
    expect(isScanning({ run: run("cancelled"), live: live({ active: true, attached: true }) })).toBe(true);
  });
});

describe("isStopped", () => {
  it("is true for a run that stopped short", () => {
    expect(isStopped({ run: run("cancelled"), live: live() })).toBe(true);
    expect(isStopped({ run: run("interrupted"), live: live() })).toBe(true);
  });

  it("is false while the scan is still going", () => {
    expect(isStopped({ run: run("inspecting"), live: live() })).toBe(false);
    expect(isStopped({ run: run("cancelled"), live: live({ active: true, attached: true }) })).toBe(false);
  });

  it("is false for a run that ended on its own, or never began", () => {
    for (const status of ["done", "indexed", "failed"] as const) {
      expect(isStopped({ run: run(status), live: live() })).toBe(false);
    }
    expect(isStopped({ run: undefined, live: live() })).toBe(false);
  });
});
