import { describe, expect, it } from "vitest";

import { STAGES, stageCalls, stageStates } from "./stages";

/** `graph/build.py`: NODES = (plan, context, triage, scout, *LENSES, skip, locate, gather, verify, reduce). */
const NODES = [
  "plan",
  "context",
  "triage",
  "scout",
  "memory",
  "injection",
  "access",
  "crypto",
  "logic",
  "skip",
  "locate",
  "gather",
  "verify",
  "reduce",
];

describe("STAGES", () => {
  it("puts every node of the pipeline in exactly one stage", () => {
    // The strip shows seven phases where the graph has fourteen nodes. A node
    // missing from here is a stage that never lights, which reads as a run that
    // skipped a step.
    const claimed = STAGES.flatMap((stage) => stage.nodes);

    expect([...claimed].sort()).toEqual([...NODES].sort());
    expect(new Set(claimed).size).toBe(claimed.length);
  });
});

describe("stageStates", () => {
  it("lights the stage whose node is in flight", () => {
    const states = stageStates(["memory", "injection"], "running");
    expect(states.lens).toBe("running");
  });

  it("counts everything before the furthest running stage as done", () => {
    // A wave revisits earlier stages, so this reads position rather than
    // counting -- a counter would tick backwards.
    const states = stageStates(["gather"], "running");
    expect(states.plan).toBe("done");
    expect(states.triage).toBe("done");
    expect(states.gather).toBe("running");
    expect(states.verify).toBe("waiting");
  });

  it("is all waiting before anything runs, and all done after", () => {
    expect(Object.values(stageStates([], "idle")).every((each) => each === "waiting")).toBe(true);
    expect(Object.values(stageStates([], "finished")).every((each) => each === "done")).toBe(true);
  });
});

describe("stageCalls", () => {
  it("adds up the nodes a stage is made of", () => {
    const counts = stageCalls([
      { node: "memory", calls: 4 },
      { node: "injection", calls: 2 },
      { node: "verify", calls: 3 },
    ]);
    expect(counts.lens).toBe(6);
    expect(counts.verify).toBe(3);
    expect(counts.plan).toBe(0);
  });
});

describe("a run that finished before the page was opened", () => {
  it("reads its stages as done, on the evidence of the calls they made", () => {
    // No stream reports a past run: the phase is `idle` and nothing is in
    // flight, so every stage read as waiting under a report full of results.
    const states = stageStates([], "idle", { triage: 4, lens: 5, verify: 2 });

    expect(states.triage).toBe("done");
    expect(states.lens).toBe("done");
    // Code rather than a model call, so it has no count of its own -- but a run
    // that reached 판정 plainly got through planning.
    expect(states.plan).toBe("done");
    // Nothing says this one ran.
    expect(states.reduce).toBe("waiting");
  });

  it("still defers to the stream while something is running", () => {
    const states = stageStates(["memory"], "running", { verify: 2 });
    expect(states.lens).toBe("running");
    // Past the running stage, so waiting -- the counts are from an earlier run
    // and the stream is the better witness.
    expect(states.verify).toBe("waiting");
  });
});
