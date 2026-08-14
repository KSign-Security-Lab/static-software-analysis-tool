import { describe, expect, it } from "vitest";

import { toolResult, whereOf } from "./tool-result";

/** What `find_definition("shorten")` actually returned on a live run. */
const DEFINITION = JSON.stringify([
  {
    chunk_id: "9a4fcb298f1cb9a5",
    file: "util.c",
    symbol: "shorten",
    kind: "function",
    start_line: 2,
    end_line: 6,
    body: "char *shorten(const char *in, char *out, int cap) {\n    strncpy(out, in, cap);\n}",
  },
]);

describe("toolResult", () => {
  it("reads the index tools' answer as the units it is", () => {
    // 295 characters of indented JSON, headed by a hash that joins two tables on
    // the server, to say a symbol is at a place and here is its body.
    const result = toolResult(DEFINITION);
    expect(result.kind).toBe("units");
    if (result.kind !== "units") return;
    expect(result.units[0]).toMatchObject({ file: "util.c", symbol: "shorten", kind: "function", startLine: 2 });
    expect(result.units[0].body).toContain("strncpy");
  });

  it("keys off the shape, not the tool's name", () => {
    // So a tool added later that answers in units is rendered as units without
    // anyone remembering to come back here.
    const result = toolResult(JSON.stringify([{ file: "a.c", symbol: "f" }]));
    expect(result.kind).toBe("units");
  });

  it("leaves a list that is not units alone", () => {
    // Not licence to hide what it contains: this pane is the audit trail.
    const result = toolResult(JSON.stringify([{ score: 1 }]));
    expect(result).toEqual({ kind: "text", text: JSON.stringify([{ score: 1 }]) });
  });

  it("keeps text as text", () => {
    const grep = "main.c:2:char *shorten(const char *in);\nutil.c:2:char *shorten(";
    expect(toolResult(grep)).toEqual({ kind: "text", text: grep });
  });

  it("keeps truncated JSON rather than losing it", () => {
    // Cut off by the store at 20,000 characters. Still the answer it gave.
    const cut = '[\n  {\n    "file": "util.c",';
    expect(toolResult(cut)).toEqual({ kind: "text", text: cut });
  });

  it("calls an empty answer empty", () => {
    // "nothing calls this" is exactly what a specialist wanted to know.
    expect(toolResult("[]").kind).toBe("empty");
    expect(toolResult("").kind).toBe("empty");
    expect(toolResult(null).kind).toBe("empty");
  });
});

describe("whereOf", () => {
  const unit = { file: "util.c", symbol: "s", kind: "function", startLine: 2, endLine: 6, body: null };

  it("names a span, a line, or a file, by what it knows", () => {
    expect(whereOf(unit)).toBe("util.c:2-6");
    expect(whereOf({ ...unit, endLine: 2 })).toBe("util.c:2");
    expect(whereOf({ ...unit, startLine: null })).toBe("util.c");
  });
});

describe("a tool that ran and refused", () => {
  /**
   * Four calls in one recorded run came back like this: the model wrote a regex
   * with an unbalanced paren, `search_text` reported it, and the reader got three
   * red lines of parser diagnostics standing where a result should be.
   */
  const BAD_REGEX = "error: invalid pattern: missing ), unterminated subpattern at position 6";

  it("is a failure, not an answer", () => {
    expect(toolResult(BAD_REGEX)).toEqual({
      kind: "failed",
      message: "invalid pattern: missing ), unterminated subpattern at position 6",
    });
  });

  it("keeps the whole message, however many lines it runs to", () => {
    const result = toolResult("Error: no such file\n  at read_source\n  path=missing.c");
    expect(result.kind).toBe("failed");
    expect(result).toMatchObject({ message: expect.stringContaining("path=missing.c") });
  });

  it("does not claim failure for text that merely mentions an error", () => {
    // `read_source` returning code is the common case, and code says "error" a
    // lot. Only a result that opens with it is treated as one.
    const source = 'if (rc < 0) { fprintf(stderr, "error: %s\\n", msg); }';
    expect(toolResult(source)).toEqual({ kind: "text", text: source });
  });

  it("still prefers the unit shape when the tool answered properly", () => {
    expect(toolResult(DEFINITION).kind).toBe("units");
  });
});
