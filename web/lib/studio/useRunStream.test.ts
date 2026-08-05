import { describe, expect, it } from "vitest";

import { IDLE, reduceRun, type RunAction } from "./useRunStream";

/** Fold a sequence of events, the way the stream delivers them. */
function play(...actions: RunAction[]) {
  return actions.reduce(reduceRun, { ...IDLE, visited: new Set<string>() });
}

const started = (node: string): RunAction => ({ type: "node_started", event: { node, step: 1 } });
const finished = (node: string): RunAction => ({ type: "node_finished", event: { node, step: 1 } });

describe("reduceRun", () => {
  it("lights up the node that is running and remembers where it has been", () => {
    const state = play(started("plan"), finished("plan"), started("context"));

    expect(state.running).toEqual(["context"]);
    expect([...state.visited].sort()).toEqual(["context", "plan"]);
    expect(state.active).toBe(true);
  });

  it("does not let a late frame blank out the node now running", () => {
    // Two nodes in flight in the view's eyes: `plan` finishing must not clear
    // the highlight `context` has taken.
    const state = play(started("plan"), started("context"), finished("plan"));

    expect(state.running).toEqual(["context"]);
  });

  it("counts a node running several times at once", () => {
    // A wave of three chunks screens in parallel: one node, three tasks. The
    // first to finish must not turn the light off for the other two.
    const state = play(started("triage"), started("triage"), started("triage"), finished("triage"));

    expect(state.running).toEqual(["triage", "triage"]);
    expect([...state.visited]).toEqual(["triage"]);

    const rest = play(
      started("triage"),
      started("triage"),
      started("triage"),
      finished("triage"),
      finished("triage"),
      finished("triage"),
    );
    expect(rest.running).toEqual([]);
  });

  it("keeps several different nodes in flight at once", () => {
    // Four specialists on one chunk. Each is its own node and all four are
    // running; a single name here would have shown whichever arrived last.
    const state = play(started("memory"), started("injection"), started("access"), started("logic"));

    expect(state.running.sort()).toEqual(["access", "injection", "logic", "memory"]);
  });

  it("bumps the revision only when the stored history moved", () => {
    const running = play(started("plan"), finished("plan"));
    expect(running.revision).toBe(0);

    const saved = reduceRun(running, {
      type: "checkpoint",
      event: { checkpoint_id: "c1", step: 1, node: "plan", next: ["context"] },
    });
    // This is what the views refetch on. A node starting is not a reason to
    // re-read the disk; a checkpoint landing is.
    expect(saved.revision).toBe(1);
    expect(saved.checkpointId).toBe("c1");
    expect(saved.queued).toEqual(["context"]);
  });

  it("holds the interrupt until something resumes it", () => {
    const stopped = play(
      started("plan"),
      finished("plan"),
      { type: "interrupted", event: { run_id: "r", next: ["analyse"], checkpoint_id: "c2" } },
    );

    expect(stopped.interrupted).toBe(true);
    expect(stopped.running).toEqual([]);
    expect(stopped.queued).toEqual(["analyse"]);
    expect(stopped.checkpointId).toBe("c2");
    // Still active: a stopped run is waiting, not over.
    expect(stopped.active).toBe(true);

    const going = reduceRun(stopped, { type: "resumed" });
    expect(going.interrupted).toBe(false);
    expect(going.active).toBe(true);
  });

  it("clears the interrupt when a node starts, so a stale pause cannot stick", () => {
    const stopped = play({ type: "interrupted", event: { run_id: "r", next: ["analyse"], checkpoint_id: "c2" } });

    expect(reduceRun(stopped, started("analyse")).interrupted).toBe(false);
  });

  it("ends the run on finish and on failure", () => {
    const done = play(started("plan"), { type: "finished" });
    expect(done).toMatchObject({ active: false, finished: true, running: [], queued: [] });

    const failed = play(started("plan"), { type: "failed", error: "no model" });
    expect(failed).toMatchObject({ active: false, running: [], error: "no model" });
  });

  it("resets between runs, so one run's history cannot colour another", () => {
    const state = play(started("plan"), { type: "reset" });

    expect(state.visited.size).toBe(0);
    expect(state.running).toEqual([]);
    expect(state.revision).toBe(0);
  });

  it("ignores a frame with no node rather than tracking an empty name", () => {
    const state = play({ type: "node_started", event: { node: null, step: 1 } });

    expect(state.running).toEqual([]);
    expect(state.visited.size).toBe(0);
  });
});
