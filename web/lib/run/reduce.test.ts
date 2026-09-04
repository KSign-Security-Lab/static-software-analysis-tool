import { describe, expect, it } from "vitest";

import { IDLE, phaseFor, phaseOf, reduceRun, scanningFiles, type RunAction, type RunLive } from "./reduce";

const node = (name: string, extra: Record<string, unknown> = {}) => ({ node: name, step: 1, ...extra });

const started = (chunk_id: string, file: string | null, remaining = 0, total = 0): RunAction => ({
  type: "chunk_started",
  event: { chunk_id, file, symbol: null, remaining, total },
});

const finished = (chunk_id: string, file: string): RunAction => ({
  type: "chunk_finished",
  event: { chunk_id, file, symbol: "f", findings: [], stats: {} },
});

/** Fold a sequence of events, the way the stream delivers them. */
function run(actions: RunAction[], from: RunLive = IDLE): RunLive {
  return actions.reduce(reduceRun, from);
}

describe("node_started / node_finished", () => {
  it("tracks the node that is running", () => {
    const state = run([{ type: "node_started", event: node("triage") }]);
    expect(state.running).toEqual(["triage"]);
    expect(state.active).toBe(true);
  });

  it("counts parallel instances rather than deduplicating them", () => {
    // Four `injection` tasks start and finish independently. A Set here would
    // make the node stop looking busy as soon as the first one returned.
    const state = run([
      { type: "node_started", event: node("injection") },
      { type: "node_started", event: node("injection") },
      { type: "node_started", event: node("injection") },
      { type: "node_started", event: node("injection") },
    ]);
    expect(state.running).toHaveLength(4);
  });

  it("removes one instance per finish, not all of them", () => {
    const state = run([
      { type: "node_started", event: node("injection") },
      { type: "node_started", event: node("injection") },
      { type: "node_finished", event: node("injection") },
    ]);
    expect(state.running).toEqual(["injection"]);
  });

  it("ignores a finish for something that never started", () => {
    const state = run([
      { type: "node_started", event: node("plan") },
      { type: "node_finished", event: node("ghost") },
    ]);
    expect(state.running).toEqual(["plan"]);
  });

  it("ignores a started event with no node", () => {
    expect(run([{ type: "node_started", event: { node: null, step: null } }]).running).toEqual([]);
  });

  it("remembers everywhere the run has been", () => {
    const state = run([
      { type: "node_started", event: node("plan") },
      { type: "node_finished", event: node("plan") },
      { type: "node_started", event: node("triage") },
    ]);
    expect([...state.visited].sort()).toEqual(["plan", "triage"]);
  });

  it("keeps an error reported by a finishing node", () => {
    const state = run([{ type: "node_finished", event: node("verify", { error: "boom" }) }]);
    expect(state.error).toBe("boom");
  });

  it("clears a stale interrupt when work resumes", () => {
    const paused = run([{ type: "interrupted", event: { run_id: "r", next: ["locate"], checkpoint_id: "c1" } }]);
    expect(paused.interrupted).toBe(true);
    expect(run([{ type: "node_started", event: node("locate") }], paused).interrupted).toBe(false);
  });
});

describe("checkpoints and interrupts", () => {
  it("bumps the revision so views know disk moved", () => {
    const state = run([{ type: "checkpoint", event: { checkpoint_id: "c1", step: 1, node: "plan", next: ["triage"] } }]);
    expect(state.revision).toBe(1);
    expect(state.checkpointId).toBe("c1");
    expect(state.queued).toEqual(["triage"]);
  });

  it("keeps the last checkpoint when an event omits one", () => {
    const state = run([
      { type: "checkpoint", event: { checkpoint_id: "c1", step: 1, node: "plan", next: [] } },
      { type: "checkpoint", event: { checkpoint_id: null, step: 2, node: "triage", next: [] } },
    ]);
    expect(state.checkpointId).toBe("c1");
  });

  it("stops showing work as running once interrupted", () => {
    const state = run([
      { type: "node_started", event: node("locate") },
      { type: "interrupted", event: { run_id: "r", next: ["locate"], checkpoint_id: "c2" } },
    ]);
    expect(state.running).toEqual([]);
    expect(state.queued).toEqual(["locate"]);
    expect(state.active).toBe(true);
  });
});

describe("resume_refused", () => {
  const refusal = { type: "refused" as const, event: { run_id: "r", error: "this step ran 4 tasks at once" } };

  it("records the refusal", () => {
    expect(run([refusal]).refusal).toMatch(/4 tasks/);
  });

  it("does not move the run", () => {
    // The server emits this and goes straight back to waiting at the same
    // checkpoint. Anything that looked like progress here would be a lie --
    // which is why the stream deliberately invalidates nothing for it.
    const paused = run([{ type: "interrupted", event: { run_id: "r", next: ["locate"], checkpoint_id: "c9" } }]);
    const after = run([refusal], paused);
    expect(after.checkpointId).toBe("c9");
    expect(after.interrupted).toBe(true);
    expect(after.revision).toBe(paused.revision);
  });

  it("clears when the run actually resumes", () => {
    expect(run([refusal, { type: "resumed" }]).refusal).toBeNull();
  });

  it("can be dismissed", () => {
    expect(run([refusal, { type: "dismiss_refusal" }]).refusal).toBeNull();
  });
});

describe("progress", () => {
  it("follows the wave and the chunk", () => {
    const state = run([
      { type: "wave_started", event: { chunks: ["a", "b"], remaining: 7 } },
      started("a", "net.c", 6, 9),
    ]);
    expect(state.wave).toEqual({ chunks: ["a", "b"], remaining: 7 });
    expect(state.chunk).toEqual({ id: "a", remaining: 6, total: 9 });
  });

  it("clears progress when the run ends", () => {
    const state = run([started("a", "net.c", 1, 2), { type: "finished", event: { run_id: "r", findings: 3, aborted: false } }]);
    expect(state.chunk).toBeNull();
    expect(state.wave).toBeNull();
    expect(scanningFiles(state).size).toBe(0);
  });
});

describe("which files are being read", () => {
  it("holds a file until every chunk of it has come back", () => {
    // Two functions of one file in the same wave. The file is still being read
    // after the first returns, and a set of file names could not say that.
    const half = run([started("a", "net.c"), started("b", "net.c"), finished("a", "net.c")]);
    expect(scanningFiles(half)).toEqual(new Set(["net.c"]));

    const done = run([finished("b", "net.c")], half);
    expect(scanningFiles(done).size).toBe(0);
  });

  it("tracks several files at once", () => {
    const state = run([started("a", "net.c"), started("b", "db.c")]);
    expect(scanningFiles(state)).toEqual(new Set(["net.c", "db.c"]));
  });

  it("remembers what it got through, which is what an aborted run leaves", () => {
    const state = run([
      started("a", "net.c"),
      finished("a", "net.c"),
      started("b", "db.c"),
      { type: "finished", event: { run_id: "r", findings: 0, aborted: true } },
    ]);
    expect(state.scanned).toEqual(new Set(["net.c"]));
    expect(scanningFiles(state).size).toBe(0);
  });

  it("survives a chunk the index no longer has", () => {
    const state = run([started("a", null), started("b", "db.c")]);
    expect(scanningFiles(state)).toEqual(new Set(["db.c"]));
  });

  it("starts over on a new run rather than carrying the last one's files", () => {
    const before = run([started("a", "net.c"), finished("a", "net.c")]);
    const next = run([{ type: "run_started", event: { run_id: "r", files_indexed: 1, files_skipped: 0, chunks: 1, links: 0 } }], before);
    expect(next.scanned.size).toBe(0);
    expect(scanningFiles(next).size).toBe(0);
  });
});

describe("attachment", () => {
  it("survives a reset, because the socket did", () => {
    const attached = run([{ type: "attached", open: true }]);
    expect(run([{ type: "reset" }], attached).attached).toBe(true);
  });

  it("returns the same object when nothing changed", () => {
    const attached = run([{ type: "attached", open: true }]);
    expect(reduceRun(attached, { type: "attached", open: true })).toBe(attached);
  });
});

describe("phaseOf", () => {
  it.each([
    ["idle", IDLE],
    ["running", run([{ type: "node_started", event: node("plan") }])],
    [
      "starting",
      run([
        { type: "run_started", event: { run_id: "r", files_indexed: 1, files_skipped: 0, chunks: 3, links: 0 } },
      ]),
    ],
    ["paused", run([{ type: "interrupted", event: { run_id: "r", next: [], checkpoint_id: "c" } }])],
    ["finished", run([{ type: "finished", event: { run_id: "r", findings: 0, aborted: false } }])],
    ["failed", run([{ type: "failed", event: { error: "nope" } }])],
  ])("reads %s", (expected, state) => {
    expect(phaseOf(state as RunLive)).toBe(expected);
  });

  it("prefers failure over anything else", () => {
    const state = run([
      { type: "node_started", event: node("plan") },
      { type: "failed", event: { error: "died" } },
    ]);
    expect(phaseOf(state)).toBe("failed");
  });
});

describe("phaseFor", () => {
  // The case this exists for: `?run=` on a finished run. The stream has heard
  // nothing, so `phaseOf` says idle -- which read as 검사 전 over a full report.
  it.each([
    ["done", "finished"],
    ["inspecting", "running"],
    ["interrupted", "paused"],
    ["failed", "failed"],
  ] as const)("falls back to the record: %s reads as %s", (status, expected) => {
    expect(phaseFor("idle", status)).toBe(expected);
  });

  it.each(["created", "indexing", "indexed"] as const)(
    "leaves %s idle, because nothing has inspected the files yet",
    (status) => {
      expect(phaseFor("idle", status)).toBe("idle");
    },
  );

  it("lets the stream win whenever it is saying anything", () => {
    // A record fetched before the run started would otherwise talk over it.
    expect(phaseFor("running", "done")).toBe("running");
    expect(phaseFor("finished", "inspecting")).toBe("finished");
  });

  it("stays idle with no record at all", () => {
    expect(phaseFor("idle", undefined)).toBe("idle");
  });
});

describe("adopting a run that was already going", () => {
  it("reads as running, with the queued nodes in flight", () => {
    // A tab that opened mid-run heard no `run_started` and no `node_started`.
    // Without this it shows an idle run: 검사 실행 enabled, canvas empty.
    const state = reduceRun(IDLE, { type: "adopted", running: ["injection", "memory"] });

    expect(phaseOf(state)).toBe("running");
    expect(state.running).toEqual(["injection", "memory"]);
    expect([...state.visited].sort()).toEqual(["injection", "memory"]);
  });

  it("is still running when the step is between checkpoints", () => {
    // No node names yet -- `starting` rather than `idle`, which is what keeps
    // the button disabled.
    expect(phaseOf(reduceRun(IDLE, { type: "adopted", running: [] }))).toBe("starting");
  });

  it("gives way to the stream once events arrive", () => {
    const adopted = reduceRun(IDLE, { type: "adopted", running: ["injection"] });
    const finished = reduceRun(adopted, {
      type: "finished",
      event: { run_id: "r", findings: 0, aborted: false },
    });

    expect(phaseOf(finished)).toBe("finished");
    expect(finished.running).toEqual([]);
  });
});

describe("cancelling", () => {
  // 중단 accepted is not 중단 done. A 200 from the cancel endpoint means the flag
  // was set; the nodes already dispatched are still returning, and the surface
  // used to claim otherwise while their findings went on arriving.
  it("does not stop the run or throw away what is in flight", () => {
    const state = run([
      { type: "run_started", event: { run_id: "r1", files_indexed: 1, files_skipped: 0, chunks: 2, links: 1 } },
      { type: "node_started", event: node("injection") },
      started("c1", "app.c", 3, 4),
      { type: "cancelling" },
    ]);

    expect(state.cancelling).toBe(true);
    // Still true, and still the truth: the wave is finishing.
    expect(state.active).toBe(true);
    expect(state.finished).toBe(false);
    expect(state.running).toEqual(["injection"]);
    expect(state.chunk).not.toBeNull();
  });

  it("keeps findings that land after the button was pressed", () => {
    const state = run([
      { type: "run_started", event: { run_id: "r1", files_indexed: 1, files_skipped: 0, chunks: 2, links: 1 } },
      { type: "cancelling" },
      finished("c1", "app.c"),
    ]);

    expect(state.cancelling).toBe(true);
    expect(state.scanned.has("app.c")).toBe(true);
  });

  it("is cleared by the run's own account of having ended", () => {
    const cancelling = run([{ type: "run_started", event: { run_id: "r1", files_indexed: 1, files_skipped: 0, chunks: 2, links: 1 } }, { type: "cancelling" }]);

    expect(reduceRun(cancelling, { type: "finished", event: { run_id: "r1", findings: 2, aborted: true } }).cancelling).toBe(false);
    expect(reduceRun(cancelling, { type: "failed", event: { error: "boom" } }).cancelling).toBe(false);
    expect(reduceRun(cancelling, { type: "reset" }).cancelling).toBe(false);
  });

  it("is idempotent, so pressing twice changes nothing", () => {
    const once = run([{ type: "cancelling" }]);
    expect(reduceRun(once, { type: "cancelling" })).toBe(once);
  });

  it("is cleared by a stop the server refused", () => {
    // The 409 is easy to get: press 중단 between the worker's last frame and its
    // `finally`. Left set, the flag disabled 중단 for the rest of the run.
    const cancelling = run([{ type: "cancelling" }]);
    expect(reduceRun(cancelling, { type: "cancel_failed" }).cancelling).toBe(false);
  });

  it("does not disturb a run nobody asked to stop", () => {
    const going = run([START]);
    expect(reduceRun(going, { type: "cancel_failed" })).toBe(going);
  });
});

const START: RunAction = {
  type: "run_started",
  event: { run_id: "r1", files_indexed: 1, files_skipped: 0, chunks: 2, links: 1 },
};

describe("starting a second run on the same id", () => {
  it("clears a stop that never landed", () => {
    // Stop, then start: the strip kept a disabled 중단하는 중 with no way to
    // press stop again, and a 1s poll of the run row open behind it for ever.
    const state = run([START, { type: "cancelling" }, START]);

    expect(state.cancelling).toBe(false);
    expect(state.active).toBe(true);
  });

  it("does not resume the last run's progress bar", () => {
    const state = run([
      START,
      { type: "wave_started", event: { chunks: ["c1"], remaining: 4 } },
      started("c1", "app.c", 3, 4),
      { type: "checkpoint", event: { checkpoint_id: "cp", step: 2, node: "plan", next: ["context"] } },
      { type: "finished", event: { run_id: "r1", findings: 1, aborted: false } },
      START,
    ]);

    expect(state.chunk).toBeNull();
    expect(state.wave).toBeNull();
    expect(state.queued).toEqual([]);
    expect(state.running).toEqual([]);
    expect(state.checkpointId).toBeNull();
    expect(state.finished).toBe(false);
    expect(state.error).toBeNull();
  });

  it("keeps the attachment, which is a fact about the socket and not the run", () => {
    const attached = run([{ type: "attached", open: true }, START]);
    expect(attached.attached).toBe(true);
  });
});
