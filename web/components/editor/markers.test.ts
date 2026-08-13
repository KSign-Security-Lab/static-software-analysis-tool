import { describe, expect, it } from "vitest";

import type { UiFinding } from "@/lib/model/finding";
import { quickFixes } from "./markers";

const model = {
  uri: { toString: () => "file:///app.c" },
  getVersionId: () => 7,
  getLineMaxColumn: () => 40,
} as never;

function finding(over: Partial<UiFinding> = {}): UiFinding {
  return {
    id: "agent:1",
    engine: "agent",
    chunkId: "c1",
    severity: "high",
    title: "버퍼 오버플로우",
    cwe: "CWE-122",
    primary: { file: "app.c", startLine: 6, startColumn: 1, endLine: 6, endColumn: 1, excerpt: "" },
    explanation: "…",
    evidence: [],
    remediation: "cap 을 버퍼 크기로 제한한다.\n\n자세히는…",
    replacement: "    shorten(name, label, sizeof(label));",
    diff: null,
    confidence: 0.9,
    verified: true,
    raw: null as never,
    ...over,
  } as UiFinding;
}

const at = (line: number) => ({ startLineNumber: line, startColumn: 1, endLineNumber: line, endColumn: 1 });

describe("quickFixes", () => {
  it("offers the fix on the line it fixes", () => {
    const { actions } = quickFixes({} as never, model, [finding()], at(6));

    expect(actions).toHaveLength(1);
    // The summary line only: `remediation` is summary and detail joined, and a
    // paragraph in a menu item is a menu item nobody can read.
    expect(actions[0].title).toBe("이대로 고치기 · cap 을 버퍼 크기로 제한한다.");
    expect(actions[0].kind).toBe("quickfix");
    const edit = actions[0].edit!.edits[0] as never as { textEdit: { text: string; range: { startLineNumber: number } } };
    expect(edit.textEdit.text).toBe("    shorten(name, label, sizeof(label));");
    expect(edit.textEdit.range.startLineNumber).toBe(6);
  });

  it("offers nothing on a line the finding does not cover", () => {
    expect(quickFixes({} as never, model, [finding()], at(20)).actions).toHaveLength(0);
  });

  it("covers every line of a multi-line finding", () => {
    const wide = finding({ primary: { ...finding().primary, startLine: 4, endLine: 8 } });
    for (const line of [4, 6, 8]) {
      expect(quickFixes({} as never, model, [wide], at(line)).actions).toHaveLength(1);
    }
  });

  it("says nothing for a finding that has advice and no code", () => {
    // A lightbulb that opened onto a paragraph would be a lightbulb that lied
    // about having a fix.
    expect(quickFixes({} as never, model, [finding({ replacement: null })], at(6)).actions).toHaveLength(0);
  });
});
