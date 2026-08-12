import { describe, expect, it } from "vitest";

import { NODE_H, NODE_W, backEdges, layoutGraph, statsFromSpans } from "./layout";
import type { GraphShape } from "@/lib/api/types";

const LOOP: GraphShape = {
  nodes: ["__start__", "plan", "context", "analyse", "__end__"],
  edges: [
    { source: "__start__", target: "plan", conditional: false },
    { source: "plan", target: "context", conditional: true },
    { source: "plan", target: "__end__", conditional: true },
    { source: "context", target: "analyse", conditional: false },
    { source: "analyse", target: "plan", conditional: false },
  ],
  mermaid: "",
  steppable: ["plan", "context", "analyse"],
  node_notes: [],
  steps: [],
};

/** Two nodes at the same depth, which the old hand-rolled layout could not do. */
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
    // The whole reason for using dagre. The previous layout put every node at
    // one x, so a branch drew both halves exactly on top of each other.
    const laid = layoutGraph(FAN_OUT);
    const at = new Map(laid.nodes.map((n) => [n.id, n.position]));

    expect(at.get("left")!.x).not.toBe(at.get("right")!.x);
    expect(at.get("left")!.y).toBe(at.get("right")!.y);
    expect(at.get("join")!.y).toBeGreaterThan(at.get("left")!.y);
  });

  it("keeps the loop back to plan without stacking the nodes on it", () => {
    const laid = layoutGraph(LOOP);
    const ys = laid.nodes.filter((n) => n.id !== "__end__").map((n) => n.position.y);

    expect(new Set(ys).size).toBe(ys.length);
    expect(laid.edges).toHaveLength(LOOP.edges.length);
  });

  it("draws every edge along the route dagre computed for it", () => {
    // dagre routes while it lays out, around whatever lies between the ends.
    // Hand-picked lanes are what put two rank-skipping edges on top of each
    // other; the only edge that still needs one is the loop, which dagre never
    // saw.
    const laid = layoutGraph(LOOP);
    const edge = (id: string) => laid.edges.find((e) => e.id === id)!;

    for (const id of ["plan->context", "context->analyse", "plan->__end__"]) {
      expect(edge(id).type).toBe("routed");
      expect(edge(id).sourceHandle).toBeUndefined();
      const points = (edge(id).data as { points: { x: number; y: number }[] }).points;
      expect(points.length).toBeGreaterThan(1);
      expect(points.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true);
    }
  });

  it("keeps the loop on a lane of its own, because nothing routed it", () => {
    // The return is left out of the dagre graph on purpose -- see layoutGraph --
    // so it has no computed route and takes the one lane that does not cut back
    // through every step it is returning past.
    const laid = layoutGraph(LOOP);
    const loop = laid.edges.find((e) => e.id === "analyse->plan")!;

    expect(loop).toMatchObject({ type: "smoothstep", sourceHandle: "right-out", targetHandle: "right-in" });
    expect(loop.className).toContain("is-loop");
  });

  it("routes an edge that skips a rank around what it skips, not through it", () => {
    // `plan -> __end__` crosses the whole column. Every bend of its route has to
    // clear the nodes in between, which is what dagre's dummy nodes are for.
    const laid = layoutGraph(LOOP);
    const points = (laid.edges.find((e) => e.id === "plan->__end__")!.data as {
      points: { x: number; y: number }[];
    }).points;
    const boxes = laid.nodes
      .filter((n) => n.id !== "plan" && n.id !== "__end__")
      .map((n) => ({ x: n.position.x, y: n.position.y }));

    for (const point of points) {
      for (const box of boxes) {
        const inside = point.x > box.x && point.x < box.x + NODE_W && point.y > box.y && point.y < box.y + NODE_H;
        expect(inside).toBe(false);
      }
    }
  });

  it("puts the end below the work rather than beside it", () => {
    // With the loop set aside `analyse` is a sink, and dagre would rank it
    // level with `__end__` -- so the graph would end in two places at once.
    const laid = layoutGraph(LOOP);
    const at = new Map(laid.nodes.map((n) => [n.id, n.position.y]));

    expect(at.get("__end__")!).toBeGreaterThan(at.get("analyse")!);
    expect(at.get("__start__")!).toBeLessThan(at.get("plan")!);
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
    // An unreachable node would leave a plain walk-from-the-entry looping or
    // silently dropping half the graph.
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

    expect(conditional.map((e) => e.id).sort()).toEqual(["plan->__end__", "plan->context"]);
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
    // Before and after are separate: stopping on the way in and stopping once
    // it has written answer different questions.
    expect(data.get("context")).toMatchObject({ queued: true, before: true, after: false });
    // LangGraph's markers are drawn, but they are not somewhere to stop.
    expect(data.get("__start__")).toMatchObject({ terminal: true });
  });
});

describe("statsFromSpans", () => {
  const span = (name: string, kind: string, latency_ms: number | null) => ({ name, kind, latency_ms });

  it("counts visits per node and averages only what was timed", () => {
    const stats = statsFromSpans([
      span("plan", "chain", 100),
      span("plan:fw.c", "chain", 300),
      // Still running, so it has no latency yet -- it counts as a visit and not
      // as a zero, which would drag the average down.
      span("plan", "chain", null),
      span("analyse:fw.c", "chain", 900),
      span("ChatOpenAI", "llm", 800),
      span("read_source", "tool", 40),
    ]);

    expect(stats.get("plan")).toEqual({ visits: 3, averageMs: 200 });
    expect(stats.get("analyse")).toEqual({ visits: 1, averageMs: 900 });
    // Model and tool calls belong to the trace, not to the node count.
    expect(stats.has("ChatOpenAI")).toBe(false);
    expect(stats.has("read_source")).toBe(false);
  });

  it("is empty for a run that has not started", () => {
    expect(statsFromSpans([]).size).toBe(0);
  });
});

describe("what each box is", () => {
  /** The real shape, in miniature: two deterministic nodes, a specialist, and the
   *  verify node that runs two steps and holds the tools. */
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
    // The question this answers: `plan` and `context` show no input and no output
    // because they never call one. Half the graph is deterministic Python and the
    // drawing gave no way to tell.
    const data = dataOf(SHAPE);

    expect(data.get("plan")).toMatchObject({ steps: [], tools: 0 });
    expect(data.get("reduce")).toMatchObject({ steps: [], tools: 0 });
    expect(data.get("triage")).toMatchObject({ steps: ["triage"], tools: 0 });
    expect(data.get("injection")).toMatchObject({ steps: ["lens:injection"], tools: 0 });
  });

  it("puts the tools on the box that holds them", () => {
    // `gather` is the only step that reaches for a tool, and it is its own node
    // so that the reaching is somewhere on the drawing at all. `verify` rules on
    // what it brought back and calls nothing.
    const data = dataOf(SHAPE);
    expect(data.get("gather")).toMatchObject({ steps: ["gather"], tools: 2 });
    expect(data.get("verify")).toMatchObject({ steps: ["verify"], tools: 0 });
  });



  it("says nothing rather than guessing when the roster has not arrived", () => {
    // A node tagged `code` because the answer had not come back would be a lie.
    const data = dataOf({ ...SHAPE, steps: [] });
    expect(data.get("plan")).toMatchObject({ roster: false });
    expect(data.get("verify")).toMatchObject({ roster: false, steps: [] });
    expect(dataOf(SHAPE).get("plan")).toMatchObject({ roster: true });
  });
});
