import { describe, expect, it } from "vitest";

import { groupByOutcome, isComplete, type Instance, type Stage } from "./types";

const instance = (over: Partial<Instance> = {}): Instance => ({
  id: "x.c",
  project: "corpus",
  cwe: "CWE-121",
  cve: "",
  outcome: "solved",
  run_id: "r1",
  config_hash: "cfg",
  contaminated: false,
  contamination_reason: "",
  matched: "exact",
  note: "",
  ...over,
});

const DETECTION: Stage[] = ["not_located", "misread", "false_flagged"];

describe("grouping by where it broke", () => {
  it("puts the failures before the passes", () => {
    const groups = groupByOutcome(
      [instance(), instance({ id: "y.c", outcome: "not_located" })],
      DETECTION,
    );
    expect(groups.map((g) => g.outcome)).toEqual(["not_located", "solved"]);
  });

  it("shows no group for a stage this dataset cannot reach", () => {
    // The corpus has no build and no test suite. A 패치 빌드 실패 bucket sitting
    // permanently at zero reads as "we never fail that way" when the truth is
    // "we never test that way".
    const groups = groupByOutcome([instance({ outcome: "not_located" })], DETECTION);
    expect(groups.some((g) => g.outcome === "patch_build_failed")).toBe(false);
  });

  it("keeps 오탐 apart from 찾고 오독", () => {
    // Two opposite failures -- wrong CWE on a real bug, and a false alarm on
    // clean code -- that need opposite fixes. One bar meaning either is a bar
    // that tells you nothing.
    const groups = groupByOutcome(
      [instance({ outcome: "misread" }), instance({ id: "y.c", outcome: "false_flagged" })],
      DETECTION,
    );
    expect(groups.map((g) => g.label)).toEqual(["찾고 오독", "오탐"]);
  });

  it("empties to nothing rather than to a row of zeroes", () => {
    expect(groupByOutcome([], DETECTION)).toEqual([]);
  });
});

describe("a baseline is a comparison only when it is complete", () => {
  it("needs a figure, a model and a source", () => {
    expect(isComplete({ name: "X", model: "m", resolved: 0.34, source: "paper" })).toBe(true);
    expect(isComplete({ name: "X", model: "", resolved: 0.34, source: "paper" })).toBe(false);
    expect(isComplete({ name: "X", model: "m", resolved: null, source: "paper" })).toBe(false);
    expect(isComplete({ name: "X", model: "m", resolved: 0.34, source: "" })).toBe(false);
  });

  it("does not mistake a zero for a missing number", () => {
    expect(isComplete({ name: "X", model: "m", resolved: 0, source: "paper" })).toBe(true);
  });
});
