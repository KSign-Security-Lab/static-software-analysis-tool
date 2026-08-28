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
 *
 * `panes` and `chrome` are the workbench's fields, and 검사 is no longer one of
 * its surfaces -- so the cross-check below has to skip it rather than assert
 * about a layout nothing computes.
 */

/** The surfaces the workbench renders. 검사 has its own shell. */
const WORKBENCH = PERSPECTIVES.filter((p) => p.id !== "agent");

describe("what each surface carries", () => {
  it("keeps the run only on 검사, which is the only surface that has one", () => {
    expect(perspective("agent").carries).toContain("run");
    for (const p of WORKBENCH) expect(p.carries).not.toContain("run");
  });

  it("drops the run on the way to a surface that does not want it", () => {
    const params = new URLSearchParams({ run: "abc123", finding: "agent:f1" });
    expect(hrefFor("f2a", params)).toBe("/f2a");
  });

  it("keeps the run on the way back to 검사", () => {
    const params = new URLSearchParams({ run: "abc123", sample: "x" });
    const href = hrefFor("agent", params);
    expect(href).toContain("run=abc123");
    // `sample` is F2-A's and 추출's; it has no meaning here.
    expect(href).not.toContain("sample");
  });

  it("carries only the run, not what is open inside it", () => {
    // `finding` and `span` are readings *of* a run and are restored with it by
    // the report, so copying them across a surface hop would name a finding the
    // destination has never heard of. `file` and `line` went with the editor.
    const carries = perspective("agent").carries;
    expect(carries).toEqual(["run"]);
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

  it("still resolves 검사, because the rail highlights it from either shell", () => {
    expect(perspectiveFor("/agent")?.id).toBe("agent");
  });

  it("is undefined off the rail, so nothing assumes a surface", () => {
    expect(perspectiveFor("/")).toBeUndefined();
    expect(perspectiveFor("/dev/tokens")).toBeUndefined();
  });

  it("answers rather than throws when the path is unknown", () => {
    // Every caller hands it `usePathname()`, which is `null` outside a router.
    expect(perspectiveFor(null)).toBeUndefined();
    expect(perspectiveFor(undefined)).toBeUndefined();
    expect(perspectiveFor("")).toBeUndefined();
  });
});

describe("declared panes", () => {
  it("names only panes the surface actually fills", () => {
    // The title bar offers a fold per entry, so an entry for a pane that is not
    // there is a button revealing a pane whose content explains it does not
    // exist.
    expect(perspective("stages").panes).toEqual(["side"]);
    expect(perspective("extract").panes).not.toContain("dock");
    expect(perspective("f2a").panes).toContain("dock");
  });

  it("says 검사 has no panes, because it has no panel group", () => {
    // Not an omission. The rail reads this to decide which folds to offer, and
    // 검사 is a flow rather than a set of resizable regions.
    expect(perspective("agent").panes).toEqual([]);
    expect(perspective("agent").chrome).toBe(false);
  });

  it("keeps `panes` and the default layout telling the same story", () => {
    // Two declarations of the same fact -- which panes exist -- and they drifted
    // once already. A pane sized to 0 that the title bar offers to unfold is a
    // control that reveals an apology.
    for (const p of WORKBENCH) {
      const layout = defaultLayoutFor(p.id);
      expect(p.panes.includes("inspector")).toBe(layout.h.inspector > 0);
      expect(p.panes.includes("dock")).toBe(layout.v.dock > 0);
    }
  });

  it("gives every workbench surface a side pane, since every one has a left list", () => {
    for (const p of WORKBENCH) expect(p.panes).toContain("side");
  });

  it("puts the shared controls in exactly one place per surface", () => {
    // `chrome` decides whether the title bar or the rail's foot carries the
    // help popover, the folds and the theme switch. Rendering both would be two
    // copies of the theme switch on one screen, so every surface must answer.
    // 벤치마크 is the workbench surface that answers no, and 검사 -- which has no
    // title bar at all -- is why the flag exists.
    expect(perspective("bench").chrome).toBe(false);
    for (const id of ["f2a", "extract", "stages"] as const) expect(perspective(id).chrome).toBe(true);
  });
});
