import { describe, expect, it } from "vitest";

import {
  DEFAULT_LAYOUT,
  cookieValue,
  decodeLayout,
  defaultLayoutFor,
  encodeLayout,
  layoutFor,
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
    const out = decodeLayout("1~agent:20_58_22_70_30~trace:1_1_1_1_1");
    expect(out.agent).toEqual(valid.agent);
    expect(out.trace).toBeUndefined();
  });
});

describe("encodeLayout", () => {
  it("emits nothing a cookie cannot hold", () => {
    const all: StoredLayout = {
      agent: valid.agent,
      trace: valid.agent,
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
    expect(layoutFor({}, "agent")).toEqual(DEFAULT_LAYOUT);
    expect(layoutFor({}, "trace")).toEqual(defaultLayoutFor("trace"));
  });

  it("gives the trace view a taller dock than the inspect view", () => {
    // The graph leads there, and the call record under it is the point.
    expect(defaultLayoutFor("trace").v.dock).toBeGreaterThan(DEFAULT_LAYOUT.v.dock);
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
      trace: valid.agent,
      f2a: valid.agent,
      extract: valid.agent,
      stages: valid.agent,
    };
    expect(cookieValue(all).length).toBeLessThan(250);
  });
});
