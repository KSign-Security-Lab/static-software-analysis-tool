import { describe, expect, it } from "vitest";

import type { UiFinding } from "@/lib/model/finding";
import type { Exchange, Unit } from "./process";
import { countKept, filterRows, rowsOf } from "./rows";

/**
 * The run as one list.
 *
 * The claim these pin is that 문제 and 기록 are one list at two settings, and the
 * thing that makes it non-trivial is the cache: a re-run reuses units, a reused
 * unit is not re-read, and its findings are in the report with no calls behind
 * them in this run. A list built from calls alone drops them -- the report says
 * 2건 and the panel shows one.
 */

function exchange(over: Partial<Exchange> = {}): Exchange {
  return {
    id: "s1",
    step: "triage",
    attempts: 1,
    node: "triage",
    subject: "handle",
    system: "",
    user: "",
    reply: null,
    offered: [],
    calls: [],
    rounds: [],
    raisedBy: null,
    from: [],
    to: [],
    latency_ms: 10,
    tokens: 10,
    error: null,
    retried: 0,
    ...over,
  };
}

function unit(over: Partial<Unit> = {}): Unit {
  return { id: "c1", symbol: "handle", file: "main.c", exchanges: [], tokens: 0, ...over };
}

function finding(over: Partial<UiFinding> = {}): UiFinding {
  return {
    id: "agent:f1",
    engine: "agent",
    chunkId: "c1",
    chunkIds: ["c1"],
    mergedIds: [],
    severity: "high",
    title: "명령어 주입",
    cwe: "CWE-78",
    primary: { file: "main.c", startLine: 6, startColumn: 1, endLine: 6, endColumn: 1, excerpt: "" },
    explanation: "",
    evidence: [],
    remediation: null,
    replacement: null,
    diff: null,
    confidence: 0.9,
    verified: true,
    raw: {} as UiFinding["raw"],
    ...over,
  };
}

/** A unit that went the whole way: screening, a specialist, evidence, a verdict. */
const WHOLE = unit({
  exchanges: [
    exchange({ id: "s-triage", step: "triage" }),
    exchange({ id: "s-lens", step: "lens:injection", subject: "handle" }),
    exchange({ id: "s-gather", step: "gather", subject: "CWE-78 main.c:6", calls: [{} as never] }),
    exchange({ id: "s-verify", step: "verify", subject: "CWE-78 main.c:6" }),
  ],
});

describe("rowsOf", () => {
  it("puts the finding where the verdict was reached, not at the end", () => {
    // So the argument reads top to bottom and the verdict row *is* the finding
    // rather than a row pointing at one.
    const [group] = rowsOf([WHOLE], [finding()]);
    expect(group.units[0].rows.map((row) => row.kind)).toEqual(["call", "call", "call", "finding"]);
    expect(group.units[0].rows.at(-1)).toMatchObject({ id: "agent:f1", call: { id: "s-verify" } });
  });

  it("prefers the verdict over the gathering, since the verdict is the decision", () => {
    const [group] = rowsOf([WHOLE], [finding()]);
    const row = group.units[0].rows.find((each) => each.kind === "finding");
    expect(row).toMatchObject({ call: { step: "verify" } });
  });

  it("falls back to the gathering when nothing verified", () => {
    // A pipeline with verification switched off still has a `gather`, and a row
    // is better than no row.
    const noVerify = unit({ exchanges: WHOLE.exchanges.filter((each) => each.step !== "verify") });
    const [group] = rowsOf([noVerify], [finding()]);
    expect(group.units[0].rows.find((each) => each.kind === "finding")).toMatchObject({
      call: { step: "gather" },
    });
  });

  it("keeps a finding whose call this run never made", () => {
    // The cache case, and the reason a row is not simply an exchange.
    const cached = unit({ exchanges: [exchange({ id: "s-triage" })] });
    const [group] = rowsOf([cached], [finding()]);

    const rows = group.units[0].rows;
    expect(rows.map((row) => row.kind)).toEqual(["call", "finding"]);
    expect(rows.at(-1)).toMatchObject({ call: null });
  });

  it("keeps a finding whose whole unit this run never touched", () => {
    const [group] = rowsOf([], [finding()]);
    expect(group.file).toBe("main.c");
    expect(group.units[0]).toMatchObject({ name: "지난 검사에서" });
    expect(group.units[0].rows).toHaveLength(1);
  });

  it("never lists one finding twice, however many chunks it was merged from", () => {
    // A merged finding carries both units' chunk ids, and both units are in the
    // run -- so the naive filter matches it in each.
    const merged = finding({ chunkIds: ["c1", "c2"], mergedIds: ["agent:f2"] });
    const second = unit({ id: "c2", symbol: "main.c", file: "main.c", exchanges: WHOLE.exchanges });
    const groups = rowsOf([WHOLE, second], [merged]);

    const findings = groups.flatMap((g) => g.units.flatMap((u) => u.rows)).filter((r) => r.kind === "finding");
    expect(findings).toHaveLength(1);
  });

  it("names a file's own chunk for what it holds", () => {
    const own = unit({ id: "c9", symbol: "main.c", file: "main.c", exchanges: [exchange()] });
    const [group] = rowsOf([own], []);
    expect(group.units[0].name).toBe("최상위 선언");
  });

  it("groups units of one file together", () => {
    const other = unit({ id: "c2", symbol: "shorten", file: "util.c", exchanges: [exchange()] });
    const groups = rowsOf([WHOLE, other], []);
    expect(groups.map((each) => each.file)).toEqual(["main.c", "util.c"]);
  });
});

describe("the filters", () => {
  const groups = rowsOf([WHOLE], [finding()]);

  it("문제 keeps only the findings", () => {
    const kept = filterRows(groups, "problems");
    expect(kept[0].units[0].rows.map((row) => row.kind)).toEqual(["finding"]);
  });

  it("전체 keeps every row", () => {
    expect(countKept(groups, "all")).toBe(4);
  });

  it("도구 keeps only the calls that reached for something", () => {
    // Not the finding, even though it is the most important row: the filter
    // means what it says, and a verdict is not a lookup.
    const kept = filterRows(groups, "tools");
    expect(kept[0].units[0].rows.map((row) => row.id)).toEqual(["s-gather"]);
  });

  it("drops a unit and a file left with nothing", () => {
    const quiet = unit({ id: "c3", symbol: "quiet", file: "quiet.c", exchanges: [exchange({ id: "s-q" })] });
    const kept = filterRows(rowsOf([WHOLE, quiet], [finding()]), "problems");
    expect(kept.map((each) => each.file)).toEqual(["main.c"]);
  });

  it("counts what each filter would show, for the name beside it", () => {
    expect(countKept(groups, "problems")).toBe(1);
    expect(countKept(groups, "tools")).toBe(1);
  });

  it("keeps a row's identity across every filter", () => {
    // The same row, not a copy per view -- which is what lets a selection
    // survive a filter change.
    const inAll = filterRows(groups, "all")[0].units[0].rows.find((r) => r.kind === "finding");
    const inProblems = filterRows(groups, "problems")[0].units[0].rows[0];
    expect(inProblems.id).toBe(inAll!.id);
  });
});
