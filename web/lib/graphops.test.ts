import { readFileSync } from "fs";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";
import { describe, expect, it } from "vitest";
import { parseCpg } from "./cpg";
import { buildViewFromLabels } from "./views";
import { contract, internalMethods, isNoise, neighborhood, scopeToMethod } from "./graphops";

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURE = resolve(here, "../../packages/ssat/tests/fixtures/f2a/cpg/update_firmware.c.json");
const cpg = () => parseCpg(JSON.parse(readFileSync(FIXTURE, "utf8")));

describe("graph reducers", () => {
  it("lists internal methods for the function picker", () => {
    const names = internalMethods(cpg()).map((m) => m.name);
    expect(names).toContain("handle_update_firmware");
    expect(names).not.toContain("system"); // external
  });

  it("scopeToMethod keeps only that function's nodes", () => {
    const c = cpg();
    const handler = internalMethods(c).find((m) => m.name === "handle_update_firmware")!;
    const ast = buildViewFromLabels(c, "ast", ["AST"]);
    const scoped = scopeToMethod(ast, c, handler.id);
    expect(scoped.nodes.length).toBeGreaterThan(0);
    expect(scoped.nodes.length).toBeLessThan(ast.nodes.length);
    for (const n of scoped.nodes) {
      expect(n.id === handler.id || c.methodOf(n.id) === handler.id).toBe(true);
    }
  });

  it("contract folds noise and reconnects, shrinking the node set", () => {
    const c = cpg();
    const ast = buildViewFromLabels(c, "ast", ["AST"]);
    const folded = contract(ast, (n) => !isNoise(n));
    expect(folded.nodes.length).toBeLessThan(ast.nodes.length);
    // no operator/literal nodes survive
    expect(folded.nodes.every((n) => !isNoise(n))).toBe(true);
  });

  it("neighborhood keeps a node and its 1-hop neighbours", () => {
    const c = cpg();
    const dfg = buildViewFromLabels(c, "dfg", ["REACHING_DEF"]);
    const some = dfg.edges[0];
    const nb = neighborhood(dfg, some.source, 1);
    expect(nb.nodes.some((n) => n.id === some.source)).toBe(true);
    expect(nb.nodes.some((n) => n.id === some.target)).toBe(true);
    expect(nb.nodes.length).toBeLessThanOrEqual(dfg.nodes.length);
  });
});
