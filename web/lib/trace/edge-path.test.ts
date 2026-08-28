import { describe, expect, it } from "vitest";

import { roundedPath } from "./edge-path";

describe("roundedPath", () => {
  it("draws a straight run as a straight line", () => {
    expect(roundedPath([{ x: 0, y: 0 }, { x: 100, y: 0 }])).toBe("M 0,0 L 100,0");
  });

  it("eases a bend instead of mitring it", () => {
    // The shape dagre hands back for an edge that steps across a rank.
    const d = roundedPath([{ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 50, y: 80 }], 10);
    expect(d).toBe("M 0,0 L 40,0 Q 50,0 50,10 L 50,80");
  });

  it("clamps the radius to half the shorter segment", () => {
    // Two bends 12px apart with a 10px radius would each eat 10px of a 12px
    // segment and cross the line they are smoothing.
    const d = roundedPath([{ x: 0, y: 0 }, { x: 12, y: 0 }, { x: 12, y: 12 }, { x: 60, y: 12 }], 10);
    expect(d).toContain("L 6,0 Q 12,0 12,6");
    expect(d).toContain("L 12,6 Q 12,12 18,12");
  });

  it("drops a repeated point rather than dividing by zero on it", () => {
    // dagre emits these where a route enters and leaves a dummy node at one
    // coordinate.
    const d = roundedPath([{ x: 0, y: 0 }, { x: 50, y: 0 }, { x: 50, y: 0 }, { x: 50, y: 40 }], 10);
    expect(d).toBe("M 0,0 L 40,0 Q 50,0 50,10 L 50,40");
    expect(d).not.toContain("NaN");
  });

  it("keeps every bend of a long route", () => {
    const points = [
      { x: 0, y: 0 },
      { x: 40, y: 0 },
      { x: 40, y: 60 },
      { x: 120, y: 60 },
      { x: 120, y: 10 },
    ];
    // Four segments, so three eased corners.
    expect(roundedPath(points).match(/Q/g)).toHaveLength(3);
  });

  it("survives a degenerate route rather than emitting a broken path", () => {
    expect(roundedPath([])).toBe("");
    expect(roundedPath([{ x: 5, y: 5 }])).toBe("M 5,5");
    expect(roundedPath([{ x: 5, y: 5 }, { x: 5, y: 5 }])).toBe("M 5,5");
  });

  it("rounds to one decimal, because the attribute is re-serialised every render", () => {
    expect(roundedPath([{ x: 0.04, y: 0 }, { x: 99.96, y: 0 }])).toBe("M 0,0 L 100,0");
  });
});
