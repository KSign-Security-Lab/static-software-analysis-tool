import { describe, expect, it } from "vitest";

import { byId, changedKeys, lanesOf } from "./lanes";
import type { Checkpoint } from "@/lib/api/studio";

function point(id: string, parent: string | null, step: number, values: Record<string, unknown> = {}): Checkpoint {
  return {
    checkpoint_id: id,
    parent_checkpoint_id: parent,
    step,
    source: "loop",
    node: "plan",
    nodes: ["plan"],
    next: [],
    created_at: null,
    values,
  };
}

describe("lanesOf", () => {
  it("keeps a run that was never forked on one line", () => {
    const lanes = lanesOf([point("a", null, 0), point("b", "a", 1), point("c", "b", 2)]);

    expect([...lanes.values()]).toEqual([0, 0, 0]);
  });

  it("puts a second child of a step on its own line", () => {
    // Writing over `a` again is what a fork is: `b` continues the original
    // course, `d` is the second-guess, and both keep their own parent.
    const lanes = lanesOf([point("a", null, 0), point("b", "a", 1), point("c", "b", 2), point("d", "a", 1)]);

    expect(lanes.get("b")).toBe(0);
    expect(lanes.get("c")).toBe(0);
    expect(lanes.get("d")).not.toBe(0);
  });

  it("survives a checkpoint whose parent is not in the window", () => {
    // History is fetched with a limit, so the oldest rows can name a parent
    // that was not returned. That must not throw or mislabel the whole run.
    const lanes = lanesOf([point("b", "cut-off", 40), point("c", "b", 41)]);

    expect(lanes.size).toBe(2);
    expect(lanes.get("c")).toBe(lanes.get("b"));
  });

  it("ignores a checkpoint with no id, which cannot be addressed anyway", () => {
    const orphan = { ...point("x", null, 0), checkpoint_id: null };

    expect(lanesOf([orphan]).size).toBe(0);
  });
});

describe("changedKeys", () => {
  const parent = point("a", null, 0, { pending: ["x", "y"], current: null, stats: { n: 1 } });

  it("names only what this step actually wrote", () => {
    // The thread is about what a node did, not about the whole state carried
    // past it -- most of which it never touched.
    const step = point("b", "a", 1, { pending: ["y"], current: "x", stats: { n: 1 } });

    expect(changedKeys(step, parent).sort()).toEqual(["current", "pending"]);
  });

  it("counts a key that did not exist before as written", () => {
    const step = point("b", "a", 1, { pending: ["x", "y"], current: null, stats: { n: 1 }, located: [] });

    expect(changedKeys(step, parent)).toEqual(["located"]);
  });

  it("treats the first step as having written everything", () => {
    expect(changedKeys(parent, undefined).sort()).toEqual(["current", "pending", "stats"]);
  });

  it("compares deeply, so an equal object is not a change", () => {
    const step = point("b", "a", 1, { pending: ["x", "y"], current: null, stats: { n: 1 } });

    expect(changedKeys(step, parent)).toEqual([]);
  });
});

describe("byId", () => {
  it("indexes the addressable checkpoints and drops the rest", () => {
    const index = byId([point("a", null, 0), { ...point("b", "a", 1), checkpoint_id: null }]);

    expect([...index.keys()]).toEqual(["a"]);
  });
});
