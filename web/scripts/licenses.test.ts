import { describe, expect, it } from "vitest";

// A plain .mjs script, deliberately dependency-free; resolved via allowJs.
import { classify, dedupe, evaluate, parseExpression, tierOf, tokenize, verify } from "./licenses.mjs";

const parse = (expr: string) => parseExpression(tokenize(expr));
const allowing =
  (...ids: string[]) =>
  (id: string) =>
    ids.includes(id);

describe("SPDX expressions", () => {
  it("reads a bare identifier", () => {
    expect(evaluate(parse("MIT"), allowing("MIT"))).toEqual({ ok: true, elected: "MIT" });
    expect(evaluate(parse("MIT"), allowing("ISC")).ok).toBe(false);
  });

  it("elects the allowed side of an OR, which is the whole point", () => {
    // dompurify ships exactly this, as a production dependency.
    const result = evaluate(parse("(MPL-2.0 OR Apache-2.0)"), allowing("Apache-2.0"));
    expect(result).toEqual({ ok: true, elected: "Apache-2.0" });
  });

  it("prefers the first allowed disjunct", () => {
    const result = evaluate(parse("MIT OR Apache-2.0"), allowing("MIT", "Apache-2.0"));
    expect(result.elected).toBe("MIT");
  });

  it("fails an OR only when no disjunct is allowed", () => {
    expect(evaluate(parse("GPL-3.0-only OR AGPL-3.0-only"), allowing("MIT"))).toEqual({ ok: false, elected: null });
  });

  it("requires every conjunct of an AND", () => {
    expect(evaluate(parse("MIT AND ISC"), allowing("MIT", "ISC"))).toEqual({ ok: true, elected: "MIT AND ISC" });
    expect(evaluate(parse("MIT AND GPL-3.0-only"), allowing("MIT")).ok).toBe(false);
  });

  it("binds WITH to its identifier rather than splitting it", () => {
    const tree = parse("GPL-2.0-only WITH Classpath-exception-2.0");
    expect(tree).toEqual({ kind: "id", id: "GPL-2.0-only WITH Classpath-exception-2.0" });
    expect(evaluate(tree, allowing("GPL-2.0-only")).ok).toBe(false);
  });

  it("gives AND tighter precedence than OR", () => {
    // MIT OR (ISC AND BSD-3-Clause) -- allowed via the right branch only.
    const tree = parse("MIT OR ISC AND BSD-3-Clause");
    expect(evaluate(tree, allowing("ISC", "BSD-3-Clause"))).toEqual({ ok: true, elected: "ISC AND BSD-3-Clause" });
  });

  it("honours parentheses over precedence", () => {
    expect(evaluate(parse("(MIT OR ISC) AND BSD-3-Clause"), allowing("MIT", "BSD-3-Clause")).ok).toBe(true);
    expect(evaluate(parse("(MIT OR ISC) AND BSD-3-Clause"), allowing("MIT")).ok).toBe(false);
  });

  it("throws rather than guessing at a malformed expression", () => {
    expect(() => parse("(MIT OR ISC")).toThrow(/unbalanced/);
    expect(() => parse("MIT OR")).toThrow(/unexpected end/);
    expect(() => parse("MIT ISC")).toThrow(/trailing tokens/);
  });
});

describe("classify", () => {
  it("accepts a plain string and the legacy object form", () => {
    expect(classify("MIT")).toEqual({ readable: true, text: "MIT" });
    expect(classify({ type: "MIT" })).toEqual({ readable: true, text: "MIT" });
  });

  it.each([undefined, null, "", { type: "" }])("refuses to read %s", (value) => {
    expect(classify(value).readable).toBe(false);
  });

  it("refuses the strings that mean 'go and look'", () => {
    expect(classify("SEE LICENSE IN LICENSE.txt").readable).toBe(false);
    expect(classify("SEE LICENCE IN COPYING").readable).toBe(false);
    expect(classify("UNKNOWN").readable).toBe(false);
    expect(classify("UNLICENSED").readable).toBe(false);
  });
});

describe("tiers", () => {
  it("puts a shipped dependency in production", () => {
    expect(tierOf({ dev: false, optional: false })).toBe("production");
  });

  it("keeps a dev platform binary in the dev tier", () => {
    // lightningcss-linux-x64-gnu is optional AND dev: it builds, it never ships.
    expect(tierOf({ dev: true, optional: true })).toBe("dev");
  });

  it("gives a shippable optional binary the strict tier", () => {
    expect(tierOf({ dev: false, optional: true })).toBe("optional");
  });

  it("treats an undeclared package as production however arborist labelled it", () => {
    // The hole this closes: arborist reports a package no manifest edge reaches
    // as `dev: true`. An `npm install --no-save elkjs` therefore sailed straight
    // through the lenient dev tier. Nothing declares it, so nothing proves it
    // does not ship.
    expect(tierOf({ dev: true, optional: false, extraneous: true })).toBe("production");
    expect(tierOf({ dev: true, optional: true, extraneous: true })).toBe("production");
  });
});

const config = {
  allow: ["MIT", "Apache-2.0"],
  denyAlways: ["AGPL-3.0-only", "UNLICENSED"],
  exceptions: {},
};

const pkg = (over: Record<string, unknown> = {}) => ({
  id: "thing@1.0.0",
  name: "thing",
  version: "1.0.0",
  license: "MIT",
  dev: false,
  optional: false,
  path: "/nowhere",
  ...over,
});

describe("verify", () => {
  const TODAY = "2026-08-05";

  it("passes a permissive production dependency", () => {
    const { failures, rows } = verify(config, [pkg()], TODAY);
    expect(failures).toEqual([]);
    expect(rows[0]).toMatchObject({ tier: "production", status: "allowed", elected: "MIT" });
  });

  it("fails a copyleft production dependency with no exception", () => {
    const { failures } = verify(config, [pkg({ license: "GPL-3.0-only" })], TODAY);
    expect(failures).toHaveLength(1);
    expect(failures[0]).toMatch(/GPL-3.0-only is not allowed and has no exception/);
  });

  it("lets an unlisted licence through in the dev tier", () => {
    const { failures, rows } = verify(config, [pkg({ license: "MPL-2.0", dev: true })], TODAY);
    expect(failures).toEqual([]);
    expect(rows[0]).toMatchObject({ tier: "dev", status: "dev" });
  });

  it("still fails a deny-listed licence in the dev tier", () => {
    const { failures } = verify(config, [pkg({ license: "AGPL-3.0-only", dev: true })], TODAY);
    expect(failures[0]).toMatch(/on the deny list/);
  });

  it("accepts a reviewed exception", () => {
    const withException = {
      ...config,
      exceptions: {
        "thing@1.0.0": { license: "LGPL-3.0-or-later", reason: "unmodified, dynamically linked", expires: "2027-01-01" },
      },
    };
    const { failures, rows } = verify(withException, [pkg({ license: "LGPL-3.0-or-later" })], TODAY);
    expect(failures).toEqual([]);
    expect(rows[0]).toMatchObject({ status: "excepted" });
  });

  it("rejects an exception with no written reason", () => {
    const withException = { ...config, exceptions: { "thing@1.0.0": { license: "LGPL-3.0-or-later", reason: "  " } } };
    const { failures } = verify(withException, [pkg({ license: "LGPL-3.0-or-later" })], TODAY);
    expect(failures[0]).toMatch(/no reason/);
  });

  it("rejects an expired exception", () => {
    const withException = {
      ...config,
      exceptions: { "thing@1.0.0": { license: "LGPL-3.0-or-later", reason: "ok", expires: "2026-01-01" } },
    };
    const { failures } = verify(withException, [pkg({ license: "LGPL-3.0-or-later" })], TODAY);
    expect(failures[0]).toMatch(/expired on 2026-01-01/);
  });

  it("forces re-review when the package changed licence under a pinned exception", () => {
    const withException = {
      ...config,
      exceptions: { "thing@1.0.0": { license: "LGPL-3.0-or-later", reason: "ok" } },
    };
    const { failures } = verify(withException, [pkg({ license: "AGPL-3.0-or-later" })], TODAY);
    expect(failures[0]).toMatch(/but the package now declares/);
  });

  it("fails a dead exception, so the allowlist cannot quietly go permissive", () => {
    const withException = { ...config, exceptions: { "gone@9.9.9": { license: "MIT", reason: "ok" } } };
    const { failures } = verify(withException, [pkg()], TODAY);
    expect(failures[0]).toMatch(/matches nothing installed/);
  });

  it("only warns for a dead platform-conditional exception", () => {
    // The libvips binaries exist on linux-x64 and not on darwin-arm64; a hard
    // failure there would make the gate unusable on half the team's machines.
    const withException = {
      ...config,
      exceptions: { "gone@9.9.9": { license: "MIT", reason: "ok", platformConditional: true } },
    };
    const { failures, warnings } = verify(withException, [pkg()], TODAY);
    expect(failures).toEqual([]);
    expect(warnings[0]).toMatch(/matches nothing installed/);
  });

  it("fails an unreadable licence rather than assuming", () => {
    const { failures } = verify(config, [pkg({ license: "SEE LICENSE IN LICENSE.txt" })], TODAY);
    expect(failures[0]).toMatch(/SEE LICENSE IN LICENSE\.txt is not allowed/);
  });

  it("fails an unparseable expression rather than substring-matching it", () => {
    const { failures } = verify(config, [pkg({ license: "MIT OR" })], TODAY);
    expect(failures[0]).toMatch(/unparseable SPDX expression/);
  });

});

describe("dedupe", () => {
  const node = (over: Record<string, unknown> = {}) => ({
    pkgid: "thing@1.0.0",
    name: "thing",
    version: "1.0.0",
    license: "MIT",
    location: "node_modules/thing",
    dev: false,
    realpath: "/nowhere",
    ...over,
  });

  it("collapses the same package at several locations into one row", () => {
    expect(dedupe([node(), node({ location: "node_modules/a/node_modules/thing" })], new Set())).toHaveLength(1);
  });

  it("lets production win over dev whichever copy is seen first", () => {
    // The stricter tier has to win, or a copyleft dependency hides behind
    // whichever copy the walk happened to reach first.
    const devFirst = dedupe([node({ dev: true }), node({ dev: false })], new Set());
    const prodFirst = dedupe([node({ dev: false }), node({ dev: true })], new Set());
    expect(devFirst[0].dev).toBe(false);
    expect(prodFirst[0].dev).toBe(false);
  });

  it("skips the root package", () => {
    expect(dedupe([node({ location: "" })], new Set())).toEqual([]);
  });

  it("marks a package listed by the optional selector", () => {
    expect(dedupe([node()], new Set(["thing@1.0.0"]))[0].optional).toBe(true);
  });

  it("marks a package listed by the extraneous selector", () => {
    expect(dedupe([node()], new Set(), new Set(["thing@1.0.0"]))[0].extraneous).toBe(true);
    expect(dedupe([node()], new Set())[0].extraneous).toBe(false);
  });
});

describe("the banned package", () => {
  const TODAY = "2026-08-05";

  it("rejects elkjs however it arrives", () => {
    // `EPL-2.0 OR GPL-3.0-or-later`: neither disjunct is permissive, so the OR
    // fails as a whole. This is the one dependency the plan bans by name, and
    // dagre already covers every layout the app needs.
    const declared = { ...pkg({ name: "elkjs", id: "elkjs@0.12.0", license: "EPL-2.0 OR GPL-3.0-or-later" }) };
    expect(verify(config, [declared], TODAY).failures[0]).toMatch(/elkjs@0\.12\.0 \[production\]/);

    const undeclared = { ...declared, dev: true, extraneous: true };
    expect(verify(config, [undeclared], TODAY).failures[0]).toMatch(/elkjs@0\.12\.0 \[production\]/);
  });
});
