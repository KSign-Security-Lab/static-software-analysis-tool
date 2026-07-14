// Verifies the browser-side CPG extraction against a real Joern export
// (the F2-A fixture). This is the frontend-unique logic: parsing GraphSON and
// projecting the AST/CG/DFG/CFG views by edge label.

import { readFileSync } from "fs";
import { dirname, resolve } from "path";
import { fileURLToPath } from "url";
import { describe, expect, it } from "vitest";
import { parseCpg } from "./cpg";
import { buildViews } from "./views";

const here = dirname(fileURLToPath(import.meta.url));
const FIXTURE = resolve(
  here,
  "../../packages/ssat/tests/fixtures/f2a/cpg/update_firmware.c.json",
);

function loadCpg() {
  return JSON.parse(readFileSync(FIXTURE, "utf8"));
}

describe("CPG extraction", () => {
  it("parses vertices, edges and node properties", () => {
    const cpg = parseCpg(loadCpg());
    expect(cpg.nodes.size).toBeGreaterThan(100);
    expect(cpg.edges.length).toBeGreaterThan(500);
    // properties are unwrapped from the VertexProperty->List shape
    const methods = [...cpg.nodes.values()].filter((n) => n.label === "METHOD");
    const names = methods.map((m) => m.name);
    expect(names).toContain("handle_update_firmware");
    expect(names).toContain("download_firmware");
    expect(names).toContain("dispatch");
  });

  it("projects an AST view (parent→child edges)", () => {
    const views = buildViews(parseCpg(loadCpg()));
    expect(views.ast.edges.length).toBeGreaterThan(0);
    expect(views.ast.nodes.length).toBeGreaterThan(0);
  });

  it("projects a CG view lifting call-sites to enclosing methods", () => {
    const views = buildViews(parseCpg(loadCpg()));
    const byId = new Map(views.cg.nodes.map((n) => [n.id, n.name]));
    const named = views.cg.edges.map((e) => `${byId.get(e.source)}->${byId.get(e.target)}`);
    expect(named).toContain("dispatch->handle_update_firmware");
    expect(named).toContain("handle_update_firmware->download_firmware");
    expect(named).toContain("download_firmware->system");
  });

  it("projects a DFG view with REACHING_DEF edges", () => {
    const views = buildViews(parseCpg(loadCpg()));
    expect(views.dfg.edges.length).toBeGreaterThan(0);
  });

  it("projects a CFG view with CFG edges", () => {
    const views = buildViews(parseCpg(loadCpg()));
    expect(views.cfg.edges.length).toBeGreaterThan(0);
  });
});
