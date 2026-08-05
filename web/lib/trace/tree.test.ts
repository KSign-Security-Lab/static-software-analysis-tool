import { describe, expect, it } from "vitest";

import { order, scopeTo } from "./tree";
import type { TraceSpan } from "@/lib/api/types";

function span(id: string, parent: string | null, name = id): TraceSpan {
  return {
    id,
    parent_id: parent,
    seq: 0,
    name,
    kind: "chain",
    status: "ok",
    error: null,
    started_at: 0,
    latency_ms: 1,
    tokens: null,
    meta: {},
    inputs: null,
    outputs: null,
  };
}

describe("order", () => {
  it("puts every call under the one that made it", () => {
    // The store returns spans in the order they opened, which interleaves
    // siblings as soon as anything runs nested. Reading the trace depends on
    // this being regrouped by parent.
    const rows = order([
      span("root", null),
      span("analyse", "root"),
      span("llm", "analyse"),
      span("verify", "root"),
      span("tool", "llm"),
    ]);

    expect(rows.map((r) => r.span.id)).toEqual(["root", "analyse", "llm", "tool", "verify"]);
    expect(rows.map((r) => r.depth)).toEqual([0, 1, 2, 3, 1]);
  });

  it("shows a span whose parent was never written", () => {
    // A truncated trace can reference a parent whose start was lost. Dropping
    // the child would hide work that really happened.
    const rows = order([span("orphan", "gone"), span("root", null)]);

    expect(rows.map((r) => r.span.id).sort()).toEqual(["orphan", "root"]);
    expect(rows.every((r) => r.depth === 0)).toBe(true);
  });

  it("keeps siblings in the order they were recorded", () => {
    const rows = order([span("root", null), span("b", "root"), span("a", "root")]);

    expect(rows.map((r) => r.span.id)).toEqual(["root", "b", "a"]);
  });

  it("is empty for a run that recorded nothing", () => {
    expect(order([])).toEqual([]);
  });
});

describe("scopeTo", () => {
  const rows = order([
    span("root", null, "LangGraph"),
    span("plan", "root", "plan"),
    span("verify", "root", "verify"),
    span("gather", "verify", "gather:CWE-78"),
    span("tool", "gather", "find_callers"),
    span("locate", "root", "locate"),
  ]);

  it("keeps a node's whole subtree, not just the rows named after it", () => {
    // "what did verify do" means its model calls and the tools those reached
    // for, not one row with the word verify in it.
    expect(scopeTo(rows, "verify").map((r) => r.span.id)).toEqual(["verify", "gather", "tool"]);
  });

  it("re-bases depth so the kept rows start at the left", () => {
    expect(scopeTo(rows, "verify").map((r) => r.depth)).toEqual([0, 1, 2]);
  });

  it("stops at the end of the subtree", () => {
    // `locate` is a sibling that follows it, and must not be swept in.
    expect(scopeTo(rows, "verify").map((r) => r.span.id)).not.toContain("locate");
  });

  it("matches on the node name, ignoring the subject appended to it", () => {
    expect(scopeTo(rows, "gather").map((r) => r.span.id)).toEqual(["gather", "tool"]);
  });

  it("is empty for a node that never ran", () => {
    expect(scopeTo(rows, "analyse")).toEqual([]);
  });
});
