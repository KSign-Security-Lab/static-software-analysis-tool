import { describe, expect, it } from "vitest";

import {
  DEFAULT_LAYOUT,
  cookieValue,
  decodeLayout,
  defaultLayoutFor,
  encodeLayout,
  layoutFor,
  LAYOUT_VERSION,
  type StoredLayout,
} from "./layout-cookie";

/** The current version prefix, derived: a bump must not rewrite every case below. */
const V = `${LAYOUT_VERSION}~`;

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
    for (const junk of ["not a layout", "{}", `${V}`, `${V}agent`, `${V}agent:`, `${V}:20_58_22_70_30`, "~~~"]) {
      expect(decodeLayout(junk)).toEqual({});
    }
  });

  it("discards a layout written by an older version", () => {
    expect(decodeLayout("0~agent:20_58_22_70_30")).toEqual({});
  });

  it("keeps a collapsed panel collapsed", () => {
    // A collapsible panel sits at 0, so restoring the number restores the fold.
    expect(decodeLayout(`${V}agent:0_78_22_70_30`).agent?.h.side).toBe(0);
  });

  it("drops a perspective whose sizes do not add up", () => {
    expect(decodeLayout(`${V}agent:10_10_10_70_30`)).toEqual({});
    expect(decodeLayout(`${V}agent:20_58_22_10_10`)).toEqual({});
  });

  it("tolerates the rounding a drag leaves behind", () => {
    expect(decodeLayout(`${V}agent:20.4_57.3_22.6_70_30`).agent).toBeDefined();
  });

  it("drops an entry with the wrong number of panels rather than half-applying it", () => {
    // Sizing some panels and leaving others at their defaults looks like a bug
    // and is harder to reason about than ignoring the entry.
    expect(decodeLayout(`${V}agent:20_80`)).toEqual({});
    expect(decodeLayout(`${V}agent:20_58_22_70_30_5`)).toEqual({});
  });

  it("rejects an unknown perspective", () => {
    expect(decodeLayout(`${V}nope:20_58_22_70_30`)).toEqual({});
  });

  it.each([
    ["negative", "-5_63_42_70_30"],
    ["over 100", "140_-20_-20_70_30"],
    ["not a number", "abc_58_22_70_30"],
    ["empty", "_58_22_70_30"],
    ["exponent", "1e2_0_0_70_30"],
    ["hex", "0x14_58_22_70_30"],
  ])("rejects a %s size", (_label, sizes) => {
    expect(decodeLayout(`${V}agent:${sizes}`)).toEqual({});
  });

  it("keeps the good perspectives when one is bad", () => {
    const out = decodeLayout(`${V}agent:20_58_22_70_30~f2a:1_1_1_1_1`);
    expect(out.agent).toEqual(valid.agent);
    expect(out.f2a).toBeUndefined();
  });
});

describe("a perspective that no longer exists", () => {
  it("is dropped from a cookie written before it went away", () => {
    // 트레이스 was its own route until it became a tab of 검사. Cookies from
    // then are still in browsers, and must not resurrect it.
    const out = decodeLayout(`${V}agent:20_58_22_70_30~trace:20_58_22_70_30`);
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
    expect(encodeLayout(broken)).toBe(String(LAYOUT_VERSION));
  });

  it("rounds to one decimal, which is all the panels keep anyway", () => {
    const noisy = {
      agent: { h: { side: 20.44444, main: 57.33333, inspector: 22.22223 }, v: { centre: 70, dock: 30 } },
    };
    expect(encodeLayout(noisy)).toBe(`${V}agent:20.4_57.3_22.2_70_30`);
  });
});

describe("layoutFor", () => {
  it("uses the stored layout when there is one", () => {
    expect(layoutFor(valid, "agent")).toEqual(valid.agent);
  });

  it("falls back to the perspective's own default", () => {
    expect(layoutFor({}, "f2a")).toEqual(DEFAULT_LAYOUT);
    expect(layoutFor({}, "f2a")).toEqual(defaultLayoutFor("f2a"));
  });


  it("leaves 스테이지 with neither a dock nor an inspector", () => {
    // It is a step list and one editor over a raw response, and it showed a
    // staging placeholder in each of the other two.
    expect(defaultLayoutFor("stages").h.inspector).toBe(0);
    expect(defaultLayoutFor("stages").v.dock).toBe(0);
  });

  it("rejects a layout written under a different pane set", () => {
    // Five positional numbers cannot say which pane a number belongs to, so an
    // older cookie is not translatable: v2 zeroed the inspector and the dock,
    // which under this arrangement hides both 문제 and 상세 on a screen whose
    // owner never asked for that. The version is the only thing that can refuse.
    for (const old of ["1~agent:16_60_24_58_42", "2~agent:18_82_0_100_0", "6~agent:16_61_23_60_40"]) {
      expect(decodeLayout(old)).toEqual({});
    }
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
