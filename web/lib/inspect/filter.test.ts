import { describe, expect, it } from "vitest";

import type { Severity, UiFinding } from "@/lib/model/finding";
import {
  NO_FACETS,
  UNCLASSIFIED,
  apply,
  byCwe,
  byFile,
  bySeverity,
  byStanding,
  fixableCount,
  isEmpty,
  isFixable,
  matches,
  sort,
  type Facets,
} from "./filter";

function finding(over: Partial<UiFinding> & { id: string }): UiFinding {
  return {
    engine: "agent",
    chunkId: null,
    severity: "medium",
    title: "제목",
    cwe: null,
    primary: { file: "a.c", startLine: 1, startColumn: 1, endLine: 1, endColumn: 1, excerpt: "" },
    explanation: "",
    evidence: [],
    remediation: null,
    replacement: null,
    diff: null,
    chunkIds: [],
    mergedIds: [],
    confidence: 0.5,
    verified: null,
    raw: {} as UiFinding["raw"],
    ...over,
  };
}

function facets(over: Partial<Facets>): Facets {
  return { ...NO_FACETS, ...over };
}

describe("isEmpty", () => {
  it("treats untouched facets as no opinion", () => {
    expect(isEmpty(NO_FACETS)).toBe(true);
    expect(isEmpty(facets({ query: "   " }))).toBe(true);
    expect(isEmpty(facets({ severity: new Set<Severity>(["high"]) }))).toBe(false);
  });
});

describe("matches", () => {
  const row = finding({
    id: "1",
    severity: "critical",
    cwe: "CWE-78",
    title: "셸로 넘어가는 입력",
    primary: { file: "src/app.c", startLine: 3, startColumn: 1, endLine: 3, endColumn: 1, excerpt: "" },
    verified: true,
  });

  it("accepts everything when no facet is set", () => {
    expect(matches(row, NO_FACETS)).toBe(true);
  });

  it("narrows by severity, cwe, file and standing", () => {
    expect(matches(row, facets({ severity: new Set<Severity>(["critical"]) }))).toBe(true);
    expect(matches(row, facets({ severity: new Set<Severity>(["low"]) }))).toBe(false);
    expect(matches(row, facets({ cwe: new Set(["CWE-78"]) }))).toBe(true);
    expect(matches(row, facets({ cwe: new Set(["CWE-79"]) }))).toBe(false);
    expect(matches(row, facets({ file: new Set(["src/app.c"]) }))).toBe(true);
    expect(matches(row, facets({ file: new Set(["src/other.c"]) }))).toBe(false);
    expect(matches(row, facets({ standing: new Set(["confirmed" as const]) }))).toBe(true);
    expect(matches(row, facets({ standing: new Set(["candidate" as const]) }))).toBe(false);
  });

  it("files an unclassified finding under its own bucket rather than dropping it", () => {
    const bare = finding({ id: "2", cwe: null });
    expect(matches(bare, facets({ cwe: new Set([UNCLASSIFIED]) }))).toBe(true);
    expect(matches(bare, facets({ cwe: new Set(["CWE-78"]) }))).toBe(false);
  });

  it("excludes a finding with no standing when standing is being filtered on", () => {
    // F2-A findings never go near a verifier, so `verified` is null and there is
    // no honest answer -- which is not the same as either answer.
    expect(matches(finding({ id: "3", verified: null }), facets({ standing: new Set(["confirmed" as const]) }))).toBe(
      false,
    );
  });

  it("searches the title, the cwe and the path, case-insensitively", () => {
    expect(matches(row, facets({ query: "셸로" }))).toBe(true);
    expect(matches(row, facets({ query: "cwe-78" }))).toBe(true);
    expect(matches(row, facets({ query: "SRC/APP" }))).toBe(true);
    expect(matches(row, facets({ query: "없는말" }))).toBe(false);
  });

  it("combines facets as an intersection", () => {
    const narrow = facets({ severity: new Set<Severity>(["critical"]), file: new Set(["src/other.c"]) });
    expect(matches(row, narrow)).toBe(false);
  });
});

describe("apply", () => {
  it("returns the same array when nothing is filtered", () => {
    const rows = [finding({ id: "1" })];
    expect(apply(rows, NO_FACETS)).toBe(rows);
  });

  it("keeps only the matching rows", () => {
    const rows = [finding({ id: "1", severity: "critical" }), finding({ id: "2", severity: "low" })];
    expect(apply(rows, facets({ severity: new Set<Severity>(["critical"]) })).map((r) => r.id)).toEqual(["1"]);
  });
});

describe("sort", () => {
  const rows = [
    finding({ id: "low-early", severity: "low", confidence: 0.9, primary: span("a.c", 1) }),
    finding({ id: "crit-late", severity: "critical", confidence: 0.2, primary: span("z.c", 9) }),
    finding({ id: "med-mid", severity: "medium", confidence: 0.5, primary: span("m.c", 5) }),
  ];

  function span(file: string, line: number) {
    return { file, startLine: line, startColumn: 1, endLine: line, endColumn: 1, excerpt: "" };
  }

  it("puts the worst first by severity", () => {
    expect(sort(rows, "severity").map((r) => r.id)).toEqual(["crit-late", "med-mid", "low-early"]);
  });

  it("groups a file's rows together when sorting by file", () => {
    expect(sort(rows, "file").map((r) => r.id)).toEqual(["low-early", "med-mid", "crit-late"]);
  });

  it("puts the confident rows first when sorting by confidence", () => {
    expect(sort(rows, "confidence").map((r) => r.id)).toEqual(["low-early", "med-mid", "crit-late"]);
  });

  it("does not mutate its input", () => {
    const before = rows.map((r) => r.id);
    sort(rows, "confidence");
    expect(rows.map((r) => r.id)).toEqual(before);
  });
});

describe("tallies", () => {
  const rows = [
    finding({ id: "1", severity: "critical", cwe: "CWE-78", verified: true, primary: at("src/a.c") }),
    finding({ id: "2", severity: "low", cwe: "CWE-78", verified: false, primary: at("src/a.c") }),
    finding({ id: "3", severity: "high", cwe: null, verified: true, primary: at("src/b.c") }),
  ];

  function at(file: string) {
    return { file, startLine: 1, startColumn: 1, endLine: 1, endColumn: 1, excerpt: "" };
  }

  it("counts severities worst first", () => {
    expect(bySeverity(rows)).toEqual([
      { value: "critical", count: 1 },
      { value: "high", count: 1 },
      { value: "low", count: 1 },
    ]);
  });

  it("counts cwes most frequent first, unclassified included", () => {
    expect(byCwe(rows)).toEqual([
      { value: "CWE-78", count: 2 },
      { value: UNCLASSIFIED, count: 1 },
    ]);
  });

  it("orders files by their worst finding, which is the order to open them in", () => {
    expect(byFile(rows)).toEqual([
      { value: "src/a.c", count: 2, worst: "critical" },
      { value: "src/b.c", count: 1, worst: "high" },
    ]);
  });

  it("counts standings with confirmed first and skips findings that have none", () => {
    const withNull = [...rows, finding({ id: "4", verified: null })];
    expect(byStanding(withNull)).toEqual([
      { value: "confirmed", count: 2 },
      { value: "candidate", count: 1 },
    ]);
  });
});

describe("fixability", () => {
  it("needs code, not advice", () => {
    expect(isFixable(finding({ id: "1", replacement: "int x = 1;" }))).toBe(true);
    expect(isFixable(finding({ id: "2", replacement: null }))).toBe(false);
    expect(isFixable(finding({ id: "3", replacement: "   \n " }))).toBe(false);
  });

  it("counts only the ticked rows that carry code", () => {
    const rows = [
      finding({ id: "a", replacement: "x" }),
      finding({ id: "b", replacement: null }),
      finding({ id: "c", replacement: "y" }),
    ];
    expect(fixableCount(rows, ["a", "b"])).toBe(1);
    expect(fixableCount(rows, new Set(["a", "c"]))).toBe(2);
    expect(fixableCount(rows, [])).toBe(0);
  });
});
