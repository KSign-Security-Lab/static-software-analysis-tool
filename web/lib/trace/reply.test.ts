import { describe, expect, it } from "vitest";

import { parseReply } from "./reply";

describe("parseReply", () => {
  it("splits a guided reply into fields, dropping the empty ones", () => {
    // What the trace actually holds for a 선별 call. As one string it is a wall of
    // braces; as fields it is an answer -- and `lenses: []` is not one of them,
    // because an empty field rendered as "없음" is a row that says nothing.
    const reply = parseReply('{"worth_analysing": false, "lenses": [], "reason": "선언만 있습니다"}');

    expect(reply.kind).toBe("fields");
    if (reply.kind !== "fields") return;
    expect(reply.fields.map((each) => each.key)).toEqual(["worth_analysing", "reason"]);
    expect(reply.fields[0].value).toBe("false");
    expect(reply.fields[1].value).toBe("선언만 있습니다");
  });

  it("shows a list of plain values as the values", () => {
    // `누구에게 · 2개` says nothing anybody wanted to know.
    const reply = parseReply('{"lenses": ["memory", "injection"]}');
    if (reply.kind !== "fields") throw new Error("expected fields");
    expect(reply.fields[0].value).toBe("memory, injection");
  });

  it("folds a list of objects behind a count", () => {
    const reply = parseReply('{"findings": [{"cwe": "CWE-78"}, {"cwe": "CWE-120"}], "note": ""}');

    expect(reply.kind).toBe("fields");
    if (reply.kind !== "fields") return;
    // The note was empty and is gone; only the findings remain.
    expect(reply.fields).toHaveLength(1);
    expect(reply.fields[0].nested?.summary).toBe("2");
    expect(reply.fields[0].nested?.json).toContain("CWE-78");
  });

  it("is blank when every field of the answer was empty", () => {
    // The commonest specialist result there is: answered in the required shape,
    // with nothing in it. One line, not two rows of 없음.
    expect(parseReply('{"findings": [], "note": ""}')).toEqual({ kind: "blank", text: '{"findings": [], "note": ""}' });
  });

  it("keeps a tool loop's prose as prose", () => {
    const reply = parseReply("먼저 pick_target 의 정의를 봐야 합니다.");
    expect(reply).toEqual({ kind: "text", text: "먼저 pick_target 의 정의를 봐야 합니다." });
  });

  it("keeps a reply the store had to cut short", () => {
    // Truncated JSON is not parseable and is still what the model said.
    const cut = '{"findings": [{"title": "Unbounded sprin';
    expect(parseReply(cut)).toEqual({ kind: "text", text: cut });
  });

  it("is empty for a call that answered nothing", () => {
    // A structured call that failed both methods records no text at all.
    expect(parseReply(null).kind).toBe("empty");
    expect(parseReply("   ").kind).toBe("empty");
  });

  it("leaves a bare array or scalar alone -- neither is an answer with parts", () => {
    expect(parseReply('["a", "b"]').kind).toBe("text");
    expect(parseReply('"just a string"').kind).toBe("text");
  });

  it("drops a null rather than printing the word null", () => {
    expect(parseReply('{"cwe": null}').kind).toBe("blank");
    const kept = parseReply('{"cwe": null, "title": "버퍼 넘침"}');
    if (kept.kind !== "fields") throw new Error("expected fields");
    expect(kept.fields.map((each) => each.key)).toEqual(["title"]);
  });
});
