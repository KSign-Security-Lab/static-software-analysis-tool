import { describe, expect, it } from "vitest";

import { defaultLayoutFor } from "./layout-cookie";
import { PERSPECTIVES, hrefFor, perspective, perspectiveFor } from "./perspectives";

/**
 * What follows you between surfaces, and what does not.
 *
 * `carries` is the single declaration of that, and two bugs came from things
 * disagreeing with it. `useRunId` restored the session run on every surface, so
 * leaving 검사 produced `/f2a?run=…` -- the id dropped on the way out and put
 * straight back by a mechanism that had never heard of `carries`. And `centre`
 * was listed with a comment claiming it survived a round trip, which it cannot:
 * `hrefFor` copies from the params it is handed, and the hop out already dropped
 * it.
 */

describe("what each surface carries", () => {
  it("keeps the run only on 검사, which is the only surface that has one", () => {
    expect(perspective("agent").carries).toContain("run");
    for (const id of ["f2a", "extract", "stages"] as const) {
      expect(perspective(id).carries).not.toContain("run");
    }
  });

  it("drops the run on the way to a surface that does not want it", () => {
    const params = new URLSearchParams({ run: "abc123", file: "main.c" });
    expect(hrefFor("f2a", params)).toBe("/f2a");
  });

  it("keeps the run and the open file on the way back to 검사", () => {
    const params = new URLSearchParams({ run: "abc123", file: "main.c", sample: "x" });
    const href = hrefFor("agent", params);
    expect(href).toContain("run=abc123");
    expect(href).toContain("file=main.c");
    // `sample` is F2-A's and 추출's; it has no meaning here.
    expect(href).not.toContain("sample");
  });

  it("does not claim to carry `centre`, which it cannot", () => {
    // The overlay closes when you leave 검사. One rule, and a true one.
    expect(perspective("agent").carries).not.toContain("centre");
  });

  it("carries nothing when there are no params to carry", () => {
    expect(hrefFor("agent", null)).toBe("/agent");
    expect(hrefFor("agent", new URLSearchParams())).toBe("/agent");
  });
});

describe("perspectiveFor", () => {
  it("prefers the longest match, so /extract/stages is not 추출", () => {
    expect(perspectiveFor("/extract/stages")?.id).toBe("stages");
    expect(perspectiveFor("/extract")?.id).toBe("extract");
  });

  it("is undefined off the rail, so nothing assumes a surface", () => {
    expect(perspectiveFor("/")).toBeUndefined();
    expect(perspectiveFor("/dev/tokens")).toBeUndefined();
  });
});

describe("declared panes", () => {
  it("names only panes the surface actually fills", () => {
    // The title bar offers a fold per entry, so an entry for a pane that is not
    // there is a button revealing a pane whose content explains it does not
    // exist. 검사 fills all three: 탐색기, 문제, 상세.
    expect(perspective("agent").panes).toEqual(["side", "dock", "inspector"]);
    // 스테이지 is a step list and one editor, and nothing else.
    expect(perspective("stages").panes).toEqual(["side"]);
    // 추출 has a node inspector but no bottom panel.
    expect(perspective("extract").panes).not.toContain("dock");
  });

  it("keeps `panes` and the default layout telling the same story", () => {
    // Two declarations of the same fact -- which panes exist -- and they drifted
    // once already. A pane sized to 0 that the title bar offers to unfold is a
    // control that reveals an apology.
    for (const p of PERSPECTIVES) {
      const layout = defaultLayoutFor(p.id);
      expect(p.panes.includes("inspector")).toBe(layout.h.inspector > 0);
      expect(p.panes.includes("dock")).toBe(layout.v.dock > 0);
    }
  });

  it("gives every surface a side pane, since every one has a left list", () => {
    for (const p of PERSPECTIVES) expect(p.panes).toContain("side");
  });
});
