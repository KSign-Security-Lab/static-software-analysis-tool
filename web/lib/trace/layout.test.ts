import { describe, expect, it } from "vitest";

import { NODE_H, NODE_W, backEdges, layoutGraph, statsFromSpans } from "./layout";
import type { GraphShape } from "@/lib/api/types";

const LOOP: GraphShape = {
  nodes: ["__start__", "plan", "context", "analyse", "__end__"],
  edges: [
    { source: "__start__", target: "plan", conditional: false },
    { source: "plan", target: "context", conditional: true },
    { source: "plan", target: "analyse", conditional: true },
    { source: "plan", target: "__end__", conditional: true },
    { source: "context", target: "analyse", conditional: false },
    { source: "analyse", target: "plan", conditional: false },
  ],
  mermaid: "",
  steppable: ["plan", "context", "analyse"],
  node_notes: [],
  steps: [],
};

const step = (name: string, node: string) => ({
  step: name,
  node,
  prompt: name,
  schema: null,
  schema_fields: [],
  tools: [],
  tools_enabled: false,
  max_tool_calls: 0,
  enabled: true,
});

const LENSES: GraphShape = {
  nodes: ["scout", "memory", "injection", "crypto", "locate"],
  edges: [
    { source: "scout", target: "memory", conditional: true },
    { source: "scout", target: "injection", conditional: true },
    { source: "scout", target: "crypto", conditional: true },
    { source: "memory", target: "locate", conditional: false },
    { source: "injection", target: "locate", conditional: false },
    { source: "crypto", target: "locate", conditional: false },
  ],
  mermaid: "",
  steppable: ["scout", "memory", "injection", "crypto", "locate"],
  node_notes: [],
  steps: [step("scout", "scout"), step("lens:memory", "memory"), step("lens:injection", "injection"), step("lens:crypto", "crypto")],
};

const FAN_OUT: GraphShape = {
  nodes: ["root", "left", "right", "join"],
  edges: [
    { source: "root", target: "left", conditional: false },
    { source: "root", target: "right", conditional: false },
    { source: "left", target: "join", conditional: false },
    { source: "right", target: "join", conditional: false },
  ],
  mermaid: "",
  steppable: ["root", "left", "right", "join"],
  node_notes: [],
  steps: [],
};

describe("layoutGraph", () => {
  it("gives siblings at the same depth different positions", () => {
    const laid = layoutGraph(FAN_OUT);
    const at = new Map(laid.nodes.map((n) => [n.id, n.position]));

    expect(at.get("left")!.x).not.toBe(at.get("right")!.x);
    expect(at.get("left")!.y).toBe(at.get("right")!.y);
    expect(at.get("join")!.y).toBeGreaterThan(at.get("left")!.y);
  });

  it("does not draw LangGraph's own terminals", () => {
    const laid = layoutGraph(LOOP);
    const ids = laid.nodes.map((n) => n.id);

    expect(ids).not.toContain("__start__");
    expect(ids).not.toContain("__end__");
    expect(laid.edges.map((e) => e.id)).not.toContain("plan->__end__");
  });

  it("marks the node the run can finish at, since the box it pointed to is gone", () => {
    const data = new Map(layoutGraph(LOOP).nodes.map((n) => [n.id, n.data]));

    expect(data.get("plan")).toMatchObject({ exits: true });
    expect(data.get("analyse")).toMatchObject({ exits: false });
  });

  it("keeps the loop back to plan without stacking the nodes on it", () => {
    const laid = layoutGraph(LOOP);
    const ys = laid.nodes.map((n) => n.position.y);

    expect(new Set(ys).size).toBe(ys.length);
    expect(laid.edges).toHaveLength(4);
  });

  it("draws every edge along the route dagre computed for it", () => {
    const laid = layoutGraph(LOOP);
    const edge = (id: string) => laid.edges.find((e) => e.id === id)!;

    for (const id of ["plan->context", "context->analyse", "plan->analyse"]) {
      expect(edge(id).type).toBe("routed");
      expect(edge(id).sourceHandle).toBeUndefined();
      const points = (edge(id).data as { points: { x: number; y: number }[] }).points;
      expect(points.length).toBeGreaterThan(1);
      expect(points.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true);
    }
  });

  it("keeps the loop on a lane of its own, because nothing routed it", () => {
    const laid = layoutGraph(LOOP);
    const loop = laid.edges.find((e) => e.id === "analyse->plan")!;

    expect(loop).toMatchObject({ type: "routed", sourceHandle: "right-out", targetHandle: "right-in" });
    expect((loop.data as { points?: unknown }).points).toBeUndefined();
    expect(loop.className).toContain("is-loop");
  });

  it("names every edge that a router picks, and the one that returns", () => {
    const laid = layoutGraph(LOOP);
    const label = (id: string) => (laid.edges.find((e) => e.id === id)!.data as { label?: string }).label;

    expect(label("analyse->plan")).toBe("되돌아가기");
    expect(label("plan->context")).toBe("조건");
    expect(label("context->analyse")).toBeUndefined();
  });

  it("uses the router's own name when the graph gives one", () => {
    const laid = layoutGraph({
      ...LOOP,
      node_notes: [
        { node: "plan", agent: false, steps: [], calls: 0, tools: 0, does: "", reads: [], writes: [], router: "has_work", rule: "", routes: [] },
      ],
    });
    const label = (id: string) => (laid.edges.find((e) => e.id === id)!.data as { label?: string }).label;

    expect(label("plan->context")).toBe("has_work");
    expect(label("plan->analyse")).toBe("has_work");
  });

  it("routes an edge that skips a rank around what it skips, not through it", () => {
    const laid = layoutGraph(LOOP);
    const points = (laid.edges.find((e) => e.id === "plan->analyse")!.data as {
      points: { x: number; y: number }[];
    }).points;
    const boxes = laid.nodes
      .filter((n) => n.id !== "plan" && n.id !== "analyse")
      .map((n) => ({ x: n.position.x, y: n.position.y }));

    for (const point of points) {
      for (const box of boxes) {
        const inside = point.x > box.x && point.x < box.x + NODE_W && point.y > box.y && point.y < box.y + NODE_H;
        expect(inside).toBe(false);
      }
    }
  });

  it("marks the loop so it is not drawn as another step", () => {
    const laid = layoutGraph(LOOP);
    const looping = laid.edges.filter((e) => e.className?.includes("is-loop"));

    expect(looping.map((e) => e.id)).toEqual(["analyse->plan"]);
  });
});

describe("backEdges", () => {
  it("finds the edge that closes the loop, not the one that opens it", () => {
    expect([...backEdges(LOOP)]).toEqual(["analyse->plan"]);
  });

  it("finds nothing in a graph with no cycle", () => {
    expect(backEdges(FAN_OUT).size).toBe(0);
  });

  it("terminates on a graph whose entry cannot reach everything", () => {
    const orphaned: GraphShape = {
      nodes: ["__start__", "a", "island", "b"],
      edges: [
        { source: "__start__", target: "a", conditional: false },
        { source: "island", target: "b", conditional: false },
        { source: "b", target: "island", conditional: false },
      ],
      mermaid: "",
      steppable: ["a", "island", "b"],
      steps: [],
      node_notes: [],
    };

    expect([...backEdges(orphaned)]).toEqual(["b->island"]);
  });

  it("marks a conditional edge as one", () => {
    const laid = layoutGraph(LOOP);
    const conditional = laid.edges.filter((e) => e.className?.includes("is-conditional"));

    expect(conditional.map((e) => e.id).sort()).toEqual(["plan->analyse", "plan->context"]);
  });

  it("carries the run onto the shape", () => {
    const laid = layoutGraph(LOOP, {
      stats: new Map([["plan", { visits: 3, averageMs: 120 }]]),
      running: ["analyse"],
      queued: ["context"],
      before: ["context"],
      after: ["plan"],
    });
    const data = new Map(laid.nodes.map((n) => [n.id, n.data]));

    expect(data.get("plan")).toMatchObject({ visits: 3, averageMs: 120, running: 0, after: true });
    expect(data.get("analyse")).toMatchObject({ running: 1, visits: 0 });
    expect(data.get("context")).toMatchObject({ queued: true, before: true, after: false });
  });
});

describe("the specialists, as one node", () => {
  it("collapses them, and the fan with them", () => {
    const laid = layoutGraph(LENSES);
    const ids = laid.nodes.map((n) => n.id).sort();

    expect(ids).toEqual(["lens:*", "locate", "scout"]);
    expect(laid.edges.map((e) => e.id).sort()).toEqual(["lens:*->locate", "scout->lens:*"]);
  });

  it("says what it stands in for", () => {
    const group = layoutGraph(LENSES).nodes.find((n) => n.id === "lens:*")!;

    expect(group.data.members).toEqual(["memory", "injection", "crypto"]);
    expect(group.data.label).toBe("전문가 분석");
  });

  it("adds up the run across all of them", () => {
    const group = layoutGraph(LENSES, {
      stats: new Map([
        ["memory", { visits: 2, averageMs: 100 }],
        ["crypto", { visits: 1, averageMs: 50 }],
      ]),
      running: ["injection", "memory"],
    }).nodes.find((n) => n.id === "lens:*")!;

    expect(group.data.visits).toBe(3);
    expect(group.data.running).toBe(2);
  });

  it("names the one that produced the claim being read", () => {
    const group = layoutGraph(LENSES, { litLenses: ["triage", "injection"] }).nodes.find(
      (n) => n.id === "lens:*",
    )!;

    expect(group.data.litMembers).toEqual(["injection"]);
  });

  it("draws all five when asked", () => {
    const laid = layoutGraph(LENSES, { expanded: true });

    expect(laid.nodes.map((n) => n.id)).toContain("memory");
    expect(laid.nodes.map((n) => n.id)).not.toContain("lens:*");
    expect(laid.edges).toHaveLength(6);
  });

  it("leaves a lone specialist alone", () => {
    const laid = layoutGraph({
      ...LENSES,
      nodes: ["scout", "memory", "locate"],
      edges: [
        { source: "scout", target: "memory", conditional: true },
        { source: "memory", target: "locate", conditional: false },
      ],
      steps: [step("lens:memory", "memory")],
    });

    expect(laid.nodes.map((n) => n.id)).toContain("memory");
    expect(laid.nodes.map((n) => n.id)).not.toContain("lens:*");
  });
});

describe("statsFromSpans", () => {
  const span = (name: string, kind: string, latency_ms: number | null) => ({ name, kind, latency_ms });

  it("counts visits per node and averages only what was timed", () => {
    const stats = statsFromSpans([
      span("plan", "chain", 100),
      span("plan:fw.c", "chain", 300),
      span("plan", "chain", null),
      span("analyse:fw.c", "chain", 900),
      span("ChatOpenAI", "llm", 800),
      span("read_source", "tool", 40),
    ]);

    expect(stats.get("plan")).toEqual({ visits: 3, averageMs: 200 });
    expect(stats.get("analyse")).toEqual({ visits: 1, averageMs: 900 });
    expect(stats.has("ChatOpenAI")).toBe(false);
    expect(stats.has("read_source")).toBe(false);
  });

  it("is empty for a run that has not started", () => {
    expect(statsFromSpans([]).size).toBe(0);
  });
});

describe("what each box is", () => {
  const SHAPE: GraphShape = {
    nodes: ["__start__", "plan", "triage", "injection", "gather", "verify", "reduce", "__end__"],
    edges: [
      { source: "__start__", target: "plan", conditional: false },
      { source: "plan", target: "triage", conditional: false },
      { source: "triage", target: "injection", conditional: true },
      { source: "injection", target: "verify", conditional: false },
      { source: "verify", target: "reduce", conditional: false },
      { source: "reduce", target: "__end__", conditional: false },
    ],
    mermaid: "",
    steppable: ["plan", "triage", "injection", "verify", "reduce"],
    node_notes: [],
    steps: [
      { step: "triage", node: "triage", prompt: "triage", schema: "Triage", schema_fields: [], tools: [], tools_enabled: false, max_tool_calls: 0, enabled: true },
      { step: "lens:injection", node: "injection", prompt: "lens:injection", schema: "ChunkAnalysis", schema_fields: [], tools: [], tools_enabled: false, max_tool_calls: 0, enabled: true },
      { step: "gather", node: "gather", prompt: "gather", schema: null, schema_fields: [], tools: [
        { name: "read_source", summary: "", parameters: [] },
        { name: "search_text", summary: "", parameters: [] },
      ], tools_enabled: true, max_tool_calls: 4, enabled: true },
      { step: "verify", node: "verify", prompt: "verify", schema: "Verdict", schema_fields: [], tools: [], tools_enabled: false, max_tool_calls: 0, enabled: true },
    ],
  };

  const dataOf = (shape: GraphShape) => new Map(layoutGraph(shape).nodes.map((n) => [n.id, n.data]));

  it("says which boxes call a model and which are plain code", () => {
    const data = dataOf(SHAPE);

    expect(data.get("plan")).toMatchObject({ steps: [], tools: 0 });
    expect(data.get("reduce")).toMatchObject({ steps: [], tools: 0 });
    expect(data.get("triage")).toMatchObject({ steps: ["triage"], tools: 0 });
    expect(data.get("injection")).toMatchObject({ steps: ["lens:injection"], tools: 0 });
  });

  it("puts the tools on the box that holds them", () => {
    const data = dataOf(SHAPE);
    expect(data.get("gather")).toMatchObject({ steps: ["gather"], tools: 2 });
    expect(data.get("verify")).toMatchObject({ steps: ["verify"], tools: 0 });
  });

  it("says nothing rather than guessing when the roster has not arrived", () => {
    const data = dataOf({ ...SHAPE, steps: [] });
    expect(data.get("plan")).toMatchObject({ roster: false });
    expect(data.get("verify")).toMatchObject({ roster: false, steps: [] });
    expect(dataOf(SHAPE).get("plan")).toMatchObject({ roster: true });
  });
});
