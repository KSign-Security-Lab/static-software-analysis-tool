import { describe, expect, it } from "vitest";

import {
  DEFAULT_LAYOUT,
  cookieValue,
  decodeLayout,
  defaultLayoutFor,
  encodeLayout,
  layoutFor,
  widths,
  type StoredLayout,
} from "./layout-cookie";

const valid: StoredLayout = {
  agent: { h: { side: 20, main: 58, inspector: 22 }, v: { centre: 70, dock: 30 } },
};

describe("decodeLayout", () => {
  it("round-trips what encodeLayout wrote", () => {
    expect(decodeLayout(encodeLayout(valid))).toEqual(valid);
  });

  it("returns empty for nothing, so a first visit gets defaults", () => {
    expect(decodeLayout(undefined)).toEqual({});
    expect(decodeLayout("")).toEqual({});
  });

  it("survives a corrupt cookie rather than blanking the app", () => {
    for (const junk of ["not a layout", "{}", "1~", "1~agent", "1~agent:", "1~:20_58_22_70_30", "~~~"]) {
      expect(decodeLayout(junk)).toEqual({});
    }
  });

  it("discards a layout written by an older version", () => {
    expect(decodeLayout("0~agent:20_58_22_70_30")).toEqual({});
  });

  it("keeps a collapsed panel collapsed", () => {
    // A collapsible panel sits at 0, so restoring the number restores the fold.
    expect(decodeLayout("1~agent:0_78_22_70_30").agent?.h.side).toBe(0);
  });

  it("drops a perspective whose sizes do not add up", () => {
    expect(decodeLayout("1~agent:10_10_10_70_30")).toEqual({});
    expect(decodeLayout("1~agent:20_58_22_10_10")).toEqual({});
  });

  it("tolerates the rounding a drag leaves behind", () => {
    expect(decodeLayout("1~agent:20.4_57.3_22.6_70_30").agent).toBeDefined();
  });

  it("drops an entry with the wrong number of panels rather than half-applying it", () => {
    // Sizing some panels and leaving others at their defaults looks like a bug
    // and is harder to reason about than ignoring the entry.
    expect(decodeLayout("1~agent:20_80")).toEqual({});
    expect(decodeLayout("1~agent:20_58_22_70_30_5")).toEqual({});
  });

  it("rejects an unknown perspective", () => {
    expect(decodeLayout("1~nope:20_58_22_70_30")).toEqual({});
  });

  it.each([
    ["negative", "-5_63_42_70_30"],
    ["over 100", "140_-20_-20_70_30"],
    ["not a number", "abc_58_22_70_30"],
    ["empty", "_58_22_70_30"],
    ["exponent", "1e2_0_0_70_30"],
    ["hex", "0x14_58_22_70_30"],
  ])("rejects a %s size", (_label, sizes) => {
    expect(decodeLayout(`1~agent:${sizes}`)).toEqual({});
  });

  it("keeps the good perspectives when one is bad", () => {
    const out = decodeLayout("1~agent:20_58_22_70_30~f2a:1_1_1_1_1");
    expect(out.agent).toEqual(valid.agent);
    expect(out.f2a).toBeUndefined();
  });
});

describe("a perspective that no longer exists", () => {
  it("is dropped from a cookie written before it went away", () => {
    // 트레이스 was its own route until it became a tab of 검사. Cookies from
    // then are still in browsers, and must not resurrect it.
    const out = decodeLayout("1~agent:20_58_22_70_30~trace:20_58_22_70_30");
    expect(out.agent).toEqual(valid.agent);
    expect(Object.keys(out)).toEqual(["agent"]);
  });
});

describe("encodeLayout", () => {
  it("emits nothing a cookie cannot hold", () => {
    const all: StoredLayout = {
      agent: valid.agent,
      f2a: valid.agent,
      extract: valid.agent,
      stages: valid.agent,
    };
    // RFC 6265 cookie-octet: printable ASCII except whitespace, DQUOTE, comma,
    // semicolon and backslash. `:` and `~` are fine, which is why the format
    // uses them and needs no percent-encoding on the way in or out.
    expect(encodeLayout(all)).toMatch(/^[\x21\x23-\x2B\x2D-\x3A\x3C-\x5B\x5D-\x7E]+$/);
  });

  it("skips a perspective carrying a non-finite size", () => {
    const broken = { agent: { h: { side: Number.NaN, main: 58, inspector: 22 }, v: { centre: 70, dock: 30 } } };
    expect(encodeLayout(broken)).toBe("1");
  });

  it("rounds to one decimal, which is all the panels keep anyway", () => {
    const noisy = {
      agent: { h: { side: 20.44444, main: 57.33333, inspector: 22.22223 }, v: { centre: 70, dock: 30 } },
    };
    expect(encodeLayout(noisy)).toBe("1~agent:20.4_57.3_22.2_70_30");
  });
});

describe("layoutFor", () => {
  it("uses the stored layout when there is one", () => {
    expect(layoutFor(valid, "agent")).toEqual(valid.agent);
  });

  it("falls back to the perspective's own default", () => {
    expect(layoutFor({}, "f2a")).toEqual(DEFAULT_LAYOUT);
    expect(layoutFor({}, "agent")).toEqual(defaultLayoutFor("agent"));
  });

  it("gives 검사 a taller dock than the bare default", () => {
    // 문제, 호출 기록 and 상태 단계 all live under the centre there now, so
    // the dock is doing considerably more work than elsewhere.
    expect(defaultLayoutFor("agent").v.dock).toBeGreaterThan(DEFAULT_LAYOUT.v.dock);
  });
});

describe("cookieValue", () => {
  it("is scoped to the whole app and readable by the client that writes it", () => {
    const value = cookieValue(valid);
    expect(value).toMatch(/^ssat\.layout=/);
    expect(value).toContain("Path=/");
    expect(value).toContain("SameSite=Lax");
    expect(value).not.toContain("HttpOnly");
  });

  it("stays small enough to ride on every asset request", () => {
    const all: StoredLayout = {
      agent: valid.agent,
      f2a: valid.agent,
      extract: valid.agent,
      stages: valid.agent,
    };
    expect(cookieValue(all).length).toBeLessThan(250);
  });
});

describe("widths", () => {
  it("renormalises when a route declines the inspector", () => {
    // 검사 is a rail, an editor and the finding under it. The stored layout still
    // names three panels, and a two-panel group given 76% of a layout hands the
    // slack to the first one: a 614px rail beside a 921px editor.
    const sizes = widths({ side: 16, main: 60, inspector: 24 }, false);

    expect(Math.round((sizes.side ?? 0) + (sizes.main ?? 0))).toBe(100);
    expect(Math.round(sizes.side ?? 0)).toBe(21);
    expect(sizes.inspector).toBeUndefined();
  });

  it("leaves a three-panel layout exactly as stored", () => {
    const stored = { side: 16, main: 60, inspector: 24 };
    expect(widths(stored, true)).toBe(stored);
  });

  it("falls back rather than dividing by zero", () => {
    expect(widths({ side: 0, main: 0, inspector: 100 }, false)).toEqual({ side: 22, main: 78 });
  });
});
