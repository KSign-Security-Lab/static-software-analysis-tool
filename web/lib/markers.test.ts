import { describe, expect, it } from "vitest";

import type { Finding, SeverityName } from "./agent-schema";
import {
  MARKER_SEVERITY,
  countsByFile,
  evidenceDecorationsFor,
  markerSeverity,
  markersFor,
  sortFindings,
  totalCount,
  worstSeverity,
} from "./markers";

/**
 * The Finding -> Monaco mapping is the whole editor integration, so it is
 * tested directly rather than through the component.
 */

function finding(overrides: Partial<Finding> = {}): Finding {
  return {
    schema_version: "1",
    id: overrides.id ?? "f1",
    chunk_id: "c1",
    severity: overrides.severity ?? "high",
    confidence: 0.9,
    title: overrides.title ?? "Command injection",
    cwe: overrides.cwe ?? "CWE-78",
    primary: overrides.primary ?? {
      file: "app.c",
      start_line: 10,
      start_column: 5,
      end_line: 10,
      end_column: 17,
      excerpt: "system(cmd);",
    },
    explanation: "Untrusted input reaches a shell.",
    evidence: overrides.evidence,
    remediation: { summary: "Use execve", detail: "Avoid the shell." },
    verified: overrides.verified ?? true,
    ...overrides,
  } as Finding;
}

describe("markerSeverity", () => {
  it("maps critical and high onto Monaco's Error level", () => {
    expect(markerSeverity("critical")).toBe(MARKER_SEVERITY.Error);
    expect(markerSeverity("high")).toBe(MARKER_SEVERITY.Error);
  });

  it("steps medium, low and info down the scale", () => {
    expect(markerSeverity("medium")).toBe(MARKER_SEVERITY.Warning);
    expect(markerSeverity("low")).toBe(MARKER_SEVERITY.Info);
    expect(markerSeverity("info")).toBe(MARKER_SEVERITY.Hint);
  });
});

describe("markersFor", () => {
  it("carries the span through unchanged", () => {
    const [marker] = markersFor([finding()], "app.c");
    expect(marker.startLineNumber).toBe(10);
    expect(marker.startColumn).toBe(5);
    expect(marker.endColumn).toBe(17);
    expect(marker.code).toBe("f1");
    expect(marker.source).toBe("CWE-78");
  });

  it("only returns findings for the requested file", () => {
    const other = finding({
      id: "f2",
      primary: {
        file: "other.c",
        start_line: 1,
        start_column: 1,
        end_line: 1,
        end_column: 2,
        excerpt: "x",
      },
    });
    expect(markersFor([finding(), other], "app.c")).toHaveLength(1);
    expect(markersFor([finding(), other], "other.c")[0].code).toBe("f2");
  });

  it("labels an unverified finding in its message", () => {
    const [marker] = markersFor([finding({ verified: false })], "app.c");
    expect(marker.message).toContain("미검증");
  });

  it("falls back to a generic source when there is no CWE", () => {
    const [marker] = markersFor([finding({ cwe: null })], "app.c");
    expect(marker.source).toBe("agent");
  });
});

describe("evidenceDecorationsFor", () => {
  const withEvidence = finding({
    evidence: [
      {
        role: "source",
        span: {
          file: "app.c",
          start_line: 3,
          start_column: 1,
          end_line: 3,
          end_column: 9,
          excerpt: "getenv()",
        },
        note: "attacker controlled",
      },
      {
        role: "sink",
        span: {
          file: "util.c",
          start_line: 7,
          start_column: 2,
          end_line: 7,
          end_column: 8,
          excerpt: "system",
        },
        note: "the sink",
      },
    ],
  });

  it("decorates only evidence in the open file", () => {
    expect(evidenceDecorationsFor(withEvidence, "app.c")).toHaveLength(1);
    expect(evidenceDecorationsFor(withEvidence, "util.c")).toHaveLength(1);
  });

  it("styles by role so the sink reads differently from the trail", () => {
    const [decoration] = evidenceDecorationsFor(withEvidence, "util.c");
    expect(decoration.options.inlineClassName).toBe("evidence-sink");
    expect(decoration.options.hoverMessage?.value).toContain("the sink");
  });

  it("returns nothing when no finding is selected", () => {
    expect(evidenceDecorationsFor(null, "app.c")).toEqual([]);
  });

  it("tolerates a finding whose evidence key was omitted on the wire", () => {
    expect(evidenceDecorationsFor(finding({ evidence: undefined }), "app.c")).toEqual([]);
  });
});

describe("file counts", () => {
  const findings = [
    finding({ id: "a", severity: "low" }),
    finding({ id: "b", severity: "critical" }),
    finding({
      id: "c",
      severity: "medium",
      primary: {
        file: "other.c",
        start_line: 1,
        start_column: 1,
        end_line: 1,
        end_column: 2,
        excerpt: "x",
      },
    }),
  ];

  it("buckets findings per file", () => {
    const counts = countsByFile(findings);
    expect(totalCount(counts.get("app.c"))).toBe(2);
    expect(totalCount(counts.get("other.c"))).toBe(1);
  });

  it("reports the worst severity in a file, not the most common", () => {
    const counts = countsByFile(findings);
    expect(worstSeverity(counts.get("app.c"))).toBe("critical");
    expect(worstSeverity(counts.get("other.c"))).toBe("medium");
  });

  it("returns null for a file with no findings", () => {
    expect(worstSeverity(undefined)).toBeNull();
    expect(totalCount(undefined)).toBe(0);
  });
});

describe("sortFindings", () => {
  it("orders most severe first, then by position", () => {
    const order: SeverityName[] = ["info", "critical", "low", "high", "medium"];
    const sorted = sortFindings(order.map((severity, i) => finding({ id: `f${i}`, severity })));
    expect(sorted.map((f) => f.severity)).toEqual([
      "critical",
      "high",
      "medium",
      "low",
      "info",
    ]);
  });

  it("does not mutate its input", () => {
    const input = [finding({ id: "a", severity: "low" }), finding({ id: "b", severity: "critical" })];
    sortFindings(input);
    expect(input.map((f) => f.id)).toEqual(["a", "b"]);
  });
});
