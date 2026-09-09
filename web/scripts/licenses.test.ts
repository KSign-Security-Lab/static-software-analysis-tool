import { describe, expect, it } from "vitest";

// A plain .mjs script, deliberately dependency-free; resolved via allowJs.
import { assign, classify, evaluate, flatten, parseExpression, tokenize, verify } from "./licenses.mjs";

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
  const row = (id: string) => ({ id, name: id.split("@")[0], version: "1.0.0", license: "MIT" });

  it("puts a shipped dependency in production", () => {
    const [only] = assign({ production: [row("a@1.0.0")], optional: [], dev: [row("a@1.0.0")] });
    expect(only.tier).toBe("production");
  });

  it("lets production win over dev whichever listing is read first", () => {
    // The stricter tier has to win, or a copyleft dependency hides behind
    // whichever copy of it the listing happened to report.
    expect(assign({ production: [row("a@1.0.0")], dev: [row("a@1.0.0")] })[0].tier).toBe("production");
    expect(assign({ dev: [row("a@1.0.0")], production: [row("a@1.0.0")] })[0].tier).toBe("production");
  });

  it("keeps a dev platform binary in the dev tier", () => {
    // lightningcss-linux-x64-gnu: an optional dependency of a dev dependency.
    // It builds, it never ships, and no production edge reaches it.
    const [only] = assign({ production: [], optional: [], dev: [row("lightningcss-linux-x64-gnu@1.0.0")] });
    expect(only.tier).toBe("dev");
  });

  it("gives a shippable optional binary the strict tier", () => {
    // `--prod` covers optionalDependencies too, so an optional binary that a
    // production edge reaches is claimed before the whole-tree listing sees it.
    const [only] = assign({ production: [], optional: [row("b@1.0.0")], dev: [row("b@1.0.0")] });
    expect(only.tier).toBe("optional");
  });

  it("tiers everything in the tree, so nothing escapes by matching no filter", () => {
    // `--dev` is not the complement of `--prod`: it omits the optional
    // dependencies *of* dev dependencies. The third listing is unfiltered for
    // this reason, and four native binaries -- one of them MPL-2.0 -- were
    // outside the audit entirely until it was.
    const tree = [row("a@1.0.0"), row("b@1.0.0"), row("c@1.0.0")];
    const tiered = assign({ production: [row("a@1.0.0")], optional: [row("b@1.0.0")], dev: tree });
    expect(tiered.map((r) => [r.id, r.tier])).toEqual([
      ["a@1.0.0", "production"],
      ["b@1.0.0", "optional"],
      ["c@1.0.0", "dev"],
    ]);
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
  tier: "production",
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
    const { failures, rows } = verify(config, [pkg({ license: "MPL-2.0", tier: "dev" })], TODAY);
    expect(failures).toEqual([]);
    expect(rows[0]).toMatchObject({ tier: "dev", status: "dev" });
  });

  it("still fails a deny-listed licence in the dev tier", () => {
    const { failures } = verify(config, [pkg({ license: "AGPL-3.0-only", tier: "dev" })], TODAY);
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

describe("flatten", () => {
  it("reads pnpm's grouping by licence back into one row per package", () => {
    const rows = flatten({
      MIT: [{ name: "thing", versions: ["1.0.0"], paths: ["/nowhere/thing"], license: "MIT" }],
      ISC: [{ name: "other", versions: ["2.0.0"], paths: ["/nowhere/other"], license: "ISC" }],
    });
    expect(rows).toEqual([
      { id: "thing@1.0.0", name: "thing", version: "1.0.0", license: "MIT", path: "/nowhere/thing" },
      { id: "other@2.0.0", name: "other", version: "2.0.0", license: "ISC", path: "/nowhere/other" },
    ]);
  });

  it("keeps two versions of one package apart, with the path each was read from", () => {
    // They can be licensed differently, and the notices quote the licence file
    // from the directory this names.
    const rows = flatten({
      MIT: [{ name: "thing", versions: ["1.0.0", "2.0.0"], paths: ["/a/thing", "/b/thing"], license: "MIT" }],
    });
    expect(rows.map((r) => [r.id, r.path])).toEqual([
      ["thing@1.0.0", "/a/thing"],
      ["thing@2.0.0", "/b/thing"],
    ]);
  });

  it("survives an empty listing, which is what a filter matching nothing gives", () => {
    expect(flatten({})).toEqual([]);
    expect(flatten(undefined)).toEqual([]);
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

    // And in the dev tier, where an unlisted licence would otherwise pass:
    // the deny list is fatal in every tier.
    const asDev = { ...declared, tier: "dev", license: "GPL-3.0-or-later", id: "elkjs@0.12.0" };
    expect(verify({ ...config, denyAlways: ["GPL-3.0-or-later"] }, [asDev], TODAY).failures[0]).toMatch(
      /elkjs@0\.12\.0 \[dev\]/,
    );
  });
});
