import { describe, expect, it } from "vitest";

import { parsePatch } from "./StatePanel";

/**
 * What the fork button is allowed to send.
 *
 * The patch goes to LangGraph as a write over one checkpoint's state, so the
 * shapes that are *valid JSON but not a state* have to be caught here -- the
 * server would take a list and merge nothing, which looks exactly like the
 * edit having been ignored.
 */
describe("parsePatch", () => {
  it("accepts an object and returns it", () => {
    expect(parsePatch('{"wave": ["a"], "current": "a"}')).toEqual({
      values: { wave: ["a"], current: "a" },
    });
  });

  it("accepts an empty object -- a fork that changes nothing is still a fork", () => {
    expect(parsePatch("{}").values).toEqual({});
  });

  it.each(["[1, 2]", "null", '"a string"', "42"])("refuses %s, which is not a state", (text) => {
    const result = parsePatch(text);
    expect(result.values).toBeUndefined();
    expect(result.error).toContain("객체");
  });

  it("reports the parse failure rather than swallowing it", () => {
    const result = parsePatch("{ oops");
    expect(result.values).toBeUndefined();
    expect(result.error).toBeTruthy();
  });
});
