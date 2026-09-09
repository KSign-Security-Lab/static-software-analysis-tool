import { describe, expect, it } from "vitest";

import type { TraceSpan } from "@/lib/api/types";
import { failuresByClaim, failuresByUnit, failuresOf } from "./failures";

const span = (name: string, over: Partial<TraceSpan> = {}): TraceSpan => ({
  id: name,
  parent_id: null,
  seq: 0,
  name,
  kind: "llm",
  status: "ok",
  error: null,
  started_at: 0,
  latency_ms: 10,
  tokens: 100,
  meta: {},
  inputs: null,
  outputs: null,
  ...over,
});

const LIMIT = "Could not parse response content as the length limit was reached";
const REAL: TraceSpan[] = [
  span("triage:main.c"),
  span("lens:injection:handle"),
  span("lens:memory:handle", { status: "error", error: LIMIT }),
  span("lens:memory:log_line", { status: "error", error: LIMIT }),
  span("verify:CWE-78 main.c:11"),
  span("fix:CWE-78 main.c:11", { status: "error", error: LIMIT }),
  span("find_definition", { kind: "tool", status: "error", error: "no such symbol" }),
];

describe("what the run did not manage", () => {
  it("finds every model call that produced nothing", () => {
    expect(failuresOf(REAL).map((f) => f.subject)).toEqual([
      "handle",
      "log_line",
      "CWE-78 main.c:11",
    ]);
  });

  it("leaves tool calls out of it", () => {
    expect(failuresOf(REAL).some((f) => f.step === "find_definition")).toBe(false);
  });

  it("names the step in the reader's language", () => {
    const [first] = failuresOf(REAL);
    expect(first.step).toBe("lens:memory");
    expect(first.role).toBe("memory 분석");
  });

  it("says nothing about a clean run", () => {
    expect(failuresOf(REAL.filter((s) => !s.error))).toEqual([]);
  });

  const RETRIED: TraceSpan[] = [
    span("triage:log_line", { status: "error", error: LIMIT }),
    span("triage:log_line"),
    span("lens:memory:handle", { status: "error", error: LIMIT }),
    span("lens:memory:handle"),
  ];

  it("does not count a call the retry made good", () => {
    expect(failuresOf(RETRIED)).toEqual([]);
  });

  it("still counts one that failed after succeeding", () => {
    const spans = [span("lens:memory:handle"), span("lens:memory:handle", { status: "error", error: LIMIT })];
    expect(failuresOf(spans).map((f) => f.subject)).toEqual(["handle"]);
  });

  it("keeps a failure whose retry failed too", () => {
    const spans = [
      span("lens:memory:handle", { status: "error", error: LIMIT }),
      span("lens:memory:handle", { status: "error", error: LIMIT }),
    ];
    expect(failuresOf(spans)).toHaveLength(2);
  });
});

describe("which unit lost an analysis", () => {
  it("keys by the symbol the 단위 list shows", () => {
    const byUnit = failuresByUnit(REAL);
    expect(byUnit.get("handle")?.[0].role).toBe("memory 분석");
    expect(byUnit.get("log_line")).toHaveLength(1);
  });

  it("does not count a claim's failure against a unit", () => {
    expect(failuresByUnit(REAL).has("CWE-78 main.c:11")).toBe(false);
  });

  it("ignores a failed lookup pass", () => {
    const withLookup = [...REAL, span("lens:memory:shorten 조회", { status: "error", error: LIMIT })];
    expect(failuresByUnit(withLookup).get("shorten")).toBeUndefined();
  });
});

describe("which claim lost its verdict or its patch", () => {
  it("keys by the subject `claimOf` rebuilds", () => {
    expect(failuresByClaim(REAL).get("CWE-78 main.c:11")?.[0].step).toBe("fix");
  });

  it("does not count a unit's failure against a claim", () => {
    expect(failuresByClaim(REAL).has("handle")).toBe(false);
  });
});
