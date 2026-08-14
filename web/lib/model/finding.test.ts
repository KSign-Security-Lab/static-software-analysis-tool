import { describe, expect, it } from "vitest";

import type { Finding as AgentFinding } from "@/lib/agent-schema";
import type { F2AResult } from "@/lib/types";
import raw from "./__fixture.f2a.json";
import { countByFile, fromAgent, fromF2A, sortFindings, type UiFinding } from "./finding";

/**
 * The two engines are not coupled, but once a result exists it is described the
 * same way so one list and one set of markers serve both. These pin that
 * mapping -- the F2-A side against a payload the real pipeline produced.
 */

const f2a = raw as unknown as F2AResult;

function agentFinding(over: Partial<AgentFinding> = {}): AgentFinding {
  return {
    schema_version: "1",
    id: "abc",
    chunk_id: "c1",
    severity: "high",
    confidence: 0.9,
    title: "Command injection",
    cwe: "CWE-78",
    primary: {
      file: "download.c",
      start_line: 28,
      start_column: 5,
      end_line: 28,
      end_column: 48,
      excerpt: 'sprintf(cmd, "wget %s", url);',
    },
    explanation: "Untrusted input reaches a shell.",
    evidence: [
      {
        role: "sink",
        span: {
          file: "download.c",
          start_line: 29,
          start_column: 5,
          end_line: 29,
          end_column: 17,
          excerpt: "system(cmd);",
        },
        note: "the sink",
      },
    ],
    remediation: { summary: "Use execv", detail: "Avoid the shell." },
    verified: true,
    ...over,
  } as AgentFinding;
}

describe("fromF2A", () => {
  it("turns a real evidence package into a finding", () => {
    const findings = fromF2A(f2a, "update_firmware.c");
    expect(findings.length).toBeGreaterThan(0);

    const [first] = findings;
    expect(first.engine).toBe("structural");
    expect(first.id.startsWith("f2a:")).toBe(true);
    expect(first.title.length).toBeGreaterThan(0);
    expect(first.primary.startLine).toBeGreaterThan(0);
  });

  it("carries the taint trace across as evidence with roles", () => {
    const [first] = fromF2A(f2a, "update_firmware.c");
    const roles = new Set(first.evidence.map((e) => e.role));
    expect(roles.has("source")).toBe(true);
    expect(roles.has("sink")).toBe(true);
    expect(first.evidence.every((e) => e.note.length > 0)).toBe(true);
  });

  it("puts the finding on the sink line, which is what gets the marker", () => {
    const [first] = fromF2A(f2a, "update_firmware.c");
    const sink = first.evidence.filter((e) => e.role === "sink").at(-1);
    expect(sink).toBeDefined();
    expect(first.primary.startLine).toBe(sink!.span.startLine);
  });

  it("reports no verification state, because F2-A has no refute pass", () => {
    expect(fromF2A(f2a, "x.c").every((f) => f.verified === null)).toBe(true);
  });

  it("is empty for a missing result rather than throwing", () => {
    expect(fromF2A(null, "x.c")).toEqual([]);
    expect(fromF2A(undefined, "x.c")).toEqual([]);
  });
});

describe("fromAgent", () => {
  it("maps snake_case spans onto the shared shape", () => {
    const [f] = fromAgent([agentFinding()]);
    expect(f.engine).toBe("agent");
    expect(f.primary.startLine).toBe(28);
    expect(f.primary.endColumn).toBe(48);
    expect(f.evidence[0].span.startLine).toBe(29);
    expect(f.verified).toBe(true);
  });

  it("keeps the unverified flag, which the list surfaces", () => {
    const [f] = fromAgent([agentFinding({ verified: false })]);
    expect(f.verified).toBe(false);
  });

  it("tolerates an omitted evidence key", () => {
    const [f] = fromAgent([agentFinding({ evidence: undefined })]);
    expect(f.evidence).toEqual([]);
  });
});

describe("both engines in one list", () => {
  const mixed: UiFinding[] = [
    ...fromAgent([agentFinding({ id: "a1", severity: "low" })]),
    ...fromF2A(f2a, "update_firmware.c"),
    ...fromAgent([agentFinding({ id: "a2", severity: "critical" })]),
  ];

  it("ids cannot collide across engines", () => {
    expect(new Set(mixed.map((f) => f.id)).size).toBe(mixed.length);
    expect(mixed.some((f) => f.id.startsWith("agent:"))).toBe(true);
    expect(mixed.some((f) => f.id.startsWith("f2a:"))).toBe(true);
  });

  it("sorts most severe first regardless of which engine found it", () => {
    const sorted = sortFindings(mixed);
    expect(sorted[0].severity).toBe("critical");
    expect(sorted.at(-1)!.severity).toBe("low");
  });

  it("counts per file for the tree badges", () => {
    const counts = countByFile(mixed);
    expect(counts.get("download.c")?.total).toBe(2);
    expect(counts.get("download.c")?.worst).toBe("critical");
  });
});

describe("merging duplicate claims", () => {
  /**
   * The chunker makes a unit of each file's top-level declarations *and* a unit
   * of each function in it, so a problem inside a function is looked at twice
   * and reported twice: same title, same CWE, same line, two `chunk_id`s. A real
   * run against `main.c` produced exactly that -- two CWE-78 rows at main.c:6,
   * identical on screen, with nothing to tell them apart.
   */
  const twice = (over: Partial<AgentFinding> = {}) => [
    agentFinding({ id: "a", chunk_id: "file-chunk" }),
    agentFinding({ id: "b", chunk_id: "fn-chunk", ...over }),
  ];

  it("collapses the same claim reported by two units into one row", () => {
    const merged = fromAgent(twice());

    expect(merged).toHaveLength(1);
    expect(merged[0].chunkIds.sort()).toEqual(["file-chunk", "fn-chunk"]);
  });

  it("says how many units agreed, rather than repeating the row", () => {
    // What the extra copy is worth: corroboration, not noise.
    expect(fromAgent(twice())[0].mergedIds).toHaveLength(1);
  });

  it("keeps the copy that can actually fix the code", () => {
    const withFix = twice({
      remediation: {
        summary: "quote it",
        detail: "wrap the URL",
        replacement: 'snprintf(cmd, sizeof(cmd), "wget \\"%s\\"", url);',
        diff: "@@ -1 +1 @@",
      },
    } as Partial<AgentFinding>);

    const merged = fromAgent(withFix);
    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe("agent:b");
    expect(merged[0].diff).toBe("@@ -1 +1 @@");
    // The one that lost still lends its id, so a link to it resolves.
    expect(merged[0].mergedIds).toEqual(["agent:a"]);
  });

  it("leaves genuinely different claims alone", () => {
    const different = [
      agentFinding({ id: "a", chunk_id: "c1" }),
      agentFinding({ id: "b", chunk_id: "c1", cwe: "CWE-120", title: "Buffer overflow" }),
    ];
    expect(fromAgent(different)).toHaveLength(2);
  });

  it("does not merge the same claim at two different lines", () => {
    // Two calls to the same unsafe function are two problems to fix.
    const elsewhere = [
      agentFinding({ id: "a", chunk_id: "c1" }),
      agentFinding({
        id: "b",
        chunk_id: "c1",
        primary: { ...agentFinding().primary, start_line: 99, end_line: 99 },
      }),
    ];
    expect(fromAgent(elsewhere)).toHaveLength(2);
  });

  it("keeps a lone finding untouched, with its own chunk", () => {
    const [only] = fromAgent([agentFinding()]);
    expect(only.chunkIds).toEqual(["c1"]);
    expect(only.mergedIds).toEqual([]);
  });
});
