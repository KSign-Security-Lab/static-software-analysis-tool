import { describe, expect, it } from "vitest";

import { defaultLayoutFor } from "./layout-cookie";
import { PERSPECTIVES, hrefFor, perspective, perspectiveFor } from "./perspectives";

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
    expect(href).not.toContain("sample");
  });

  it("carries only the run, not what is open inside it", () => {
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
    expect(perspectiveFor(null)).toBeUndefined();
    expect(perspectiveFor(undefined)).toBeUndefined();
    expect(perspectiveFor("")).toBeUndefined();
  });
});

describe("declared panes", () => {
  it("names only panes the surface actually fills", () => {
    expect(perspective("stages").panes).toEqual(["side"]);
    expect(perspective("extract").panes).not.toContain("dock");
    expect(perspective("f2a").panes).toContain("dock");
  });

  it("says 검사 has no panes, because it has no panel group", () => {
    expect(perspective("agent").panes).toEqual([]);
    expect(perspective("agent").chrome).toBe(false);
  });

  it("keeps `panes` and the default layout telling the same story", () => {
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
    expect(perspective("bench").chrome).toBe(false);
    for (const id of ["f2a", "extract", "stages"] as const) expect(perspective(id).chrome).toBe(true);
  });
});
