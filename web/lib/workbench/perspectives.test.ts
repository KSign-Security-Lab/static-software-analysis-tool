import { describe, expect, it } from "vitest";

import { isInspectSpace, perspectiveFor } from "./perspectives";

describe("the two workspaces of 검사", () => {
  it("tells them apart by route, so each is a place you can link to", () => {
    // One surface, two workspaces: one about your code and the problems in it,
    // one about the checker that found them. They were the same screen, which is
    // why the checker's machinery kept taking space from the answer.
    expect(isInspectSpace("/agent")).toBe(true);
    expect(isInspectSpace("/agent/")).toBe(true);
    expect(isInspectSpace("/agent/machine")).toBe(false);
    expect(isInspectSpace("/f2a")).toBe(false);
  });

  it("keeps both under the 검사 rail entry", () => {
    // They share the run, the rail entry and the layout cookie; what differs is
    // which panes are worth having.
    expect(perspectiveFor("/agent")?.id).toBe("agent");
    expect(perspectiveFor("/agent/machine")?.id).toBe("agent");
  });
});
