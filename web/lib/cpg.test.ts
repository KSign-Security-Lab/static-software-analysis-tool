import { describe, expect, it } from "vitest";

import { looksLikeCpg, parseCpg, unwrapCpgDocument } from "./cpg";

/**
 * Opening a CPG JSON is the old web/ app's primary input, restored after the
 * merge dropped it. The file can arrive in either wrapper depending on what
 * produced it, so the tolerance is pinned here rather than left to a try.
 */

const GRAPHSON = {
  "@type": "tinker:graph",
  "@value": {
    vertices: [
      { id: { "@type": "g:Int64", "@value": 1 }, label: "METHOD", properties: {} },
      { id: { "@type": "g:Int64", "@value": 2 }, label: "CALL", properties: {} },
    ],
    edges: [
      {
        id: { "@type": "g:Int64", "@value": 10 },
        label: "AST",
        outV: { "@type": "g:Int64", "@value": 1 },
        inV: { "@type": "g:Int64", "@value": 2 },
      },
    ],
  },
};

describe("unwrapCpgDocument", () => {
  it("passes bare GraphSON through", () => {
    expect(unwrapCpgDocument(GRAPHSON)).toBe(GRAPHSON);
  });

  it("unwraps the {export: ...} form the pipeline writes", () => {
    expect(unwrapCpgDocument({ export: GRAPHSON })).toBe(GRAPHSON);
  });

  it("leaves anything else alone", () => {
    expect(unwrapCpgDocument([1, 2])).toEqual([1, 2]);
    expect(unwrapCpgDocument(null)).toBeNull();
  });
});

describe("looksLikeCpg", () => {
  it("accepts both wrappers", () => {
    expect(looksLikeCpg(GRAPHSON)).toBe(true);
    expect(looksLikeCpg({ export: GRAPHSON })).toBe(true);
  });

  it("rejects JSON that is not a CPG, so the drop reports it", () => {
    expect(looksLikeCpg({ hello: "world" })).toBe(false);
    expect(looksLikeCpg({ "@value": { vertices: [], edges: [] } })).toBe(false);
    expect(looksLikeCpg([])).toBe(false);
  });
});

describe("parseCpg on an unwrapped upload", () => {
  it("finds the nodes and edges the viewers draw", () => {
    const parsed = parseCpg(unwrapCpgDocument({ export: GRAPHSON }));
    expect(parsed.nodes.size).toBe(2);
    expect(parsed.edges).toHaveLength(1);
    expect([...parsed.nodes.values()].map((n) => n.label).sort()).toEqual(["CALL", "METHOD"]);
  });
});
