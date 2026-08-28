import { describe, expect, it } from "vitest";
import { nonEmptyFunctions, pipelineAstView, pipelineDfgView } from "./pipeline";
import type { PipelineFunction } from "./types";

const fn: PipelineFunction = {
  function_name: "store_charging_profile",
  ast: {
    nodes: [
      { sid: 0, node_type_id: "FunctionEntry", code: "<entry:store_charging_profile>" },
      { sid: 1, node_type_id: "ParameterDeclaration", code: "const unsigned char *schedule" },
      { sid: 2, node_type_id: "StandardLibCall", code: "memcpy(buf, schedule, len)" },
    ],
    edges_ast_pc: [
      [0, 1, 0],
      [0, 2, 0],
    ],
    edges_ast_sb: [[1, 2, 1]],
    edges_ast_guard: [{ src: 1, dst: 2, guard_kind: 2, guard_branch: 0 }],
  },
  dfg: {
    nodes: [{ sid: 1 }, { sid: 2 }],
    edges_dfg: [[1, 2, { feat: { flow_id: 1 }, debug: { var_key: "schedule" } }]],
  },
};

describe("pipelineAstView", () => {
  it("emits one node per statement and all three edge families", () => {
    const view = pipelineAstView(fn);

    expect(view.key).toBe("pipeline-ast");
    expect(view.nodes.map((n) => n.id)).toEqual(["0", "1", "2"]);
    // 2 parent/child + 1 statement-order + 1 guard
    expect(view.edges).toHaveLength(4);
    expect(view.edges.filter((e) => e.label === "next")).toHaveLength(1);
    expect(view.edges.filter((e) => e.label === "upper")).toHaveLength(1);
  });

  it("carries statement code onto the node so the graph is readable", () => {
    const memcpy = pipelineAstView(fn).nodes.find((n) => n.id === "2");
    expect(memcpy?.code).toContain("memcpy");
    expect(memcpy?.label).toBe("StandardLibCall");
  });

  it("is titled so it cannot be confused with the CPG's AST view", () => {
    expect(pipelineAstView(fn).title).toBe("AST (pipeline)");
  });
});

describe("pipelineDfgView", () => {
  it("labels each edge with the variable that flows along it", () => {
    const view = pipelineDfgView(fn);

    expect(view.key).toBe("pipeline-dfg");
    expect(view.edges).toHaveLength(1);
    expect(view.edges[0]).toMatchObject({ source: "1", target: "2", label: "schedule" });
  });

  it("borrows code from the AST, since DFG nodes carry only sids", () => {
    const node = pipelineDfgView(fn).nodes.find((n) => n.id === "2");
    expect(node?.code).toContain("memcpy");
  });

  it("falls back to the flow kind when an edge has no var_key", () => {
    const anon: PipelineFunction = {
      ...fn,
      dfg: { nodes: [{ sid: 1 }, { sid: 2 }], edges_dfg: [[1, 2, { feat: { flow_id: 3 } }]] },
    };
    expect(pipelineDfgView(anon).edges[0].label).toBe("size");
  });

  it("is titled so it cannot be confused with the CPG's DFG view", () => {
    expect(pipelineDfgView(fn).title).toBe("DFG (pipeline)");
  });
});

describe("nonEmptyFunctions", () => {
  it("drops functions the extractor produced nothing for", () => {
    const empty: PipelineFunction = {
      function_name: "declaration_only",
      ast: { nodes: [], edges_ast_pc: [], edges_ast_sb: [], edges_ast_guard: [] },
      dfg: { nodes: [], edges_dfg: [] },
    };
    expect(nonEmptyFunctions([fn, empty]).map((f) => f.function_name)).toEqual([
      "store_charging_profile",
    ]);
  });
});
