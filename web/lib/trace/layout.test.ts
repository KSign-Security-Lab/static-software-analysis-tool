import { describe, expect, it } from "vitest";

import { NODE_H, NODE_W, backEdges, layoutGraph, statsFromSpans } from "./layout";
import type { GraphShape } from "@/lib/api/types";

/**
 * As the API sends it -- terminals included.
 *
 * `layoutGraph` drops `__start__` and `__end__` before dagre sees them, so every
 * assertion below is about a graph two nodes smaller than this. That asymmetry is
 * the point: the shape is the server's and the drawing is a decision about it.
 *
 * `plan -> analyse` skips a rank on purpose, so there is still an edge that has
 * to be routed around something after `plan -> __end__` stops being drawn.
 */
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

/** A step per specialist, which is what makes them collapsible. */
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

/** The real fan, in miniature: one scout, three specialists, one join. */
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

  it("does not draw LangGraph's own terminals", () => {
    // `__start__` and `__end__` are bookkeeping. They cost two ranks, and
    // `plan -> __end__` was the longest edge on the real canvas -- routed the
    // whole way down the left gutter to say what `plan`'s router already says.
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
    // Six sent, two of them touching a terminal.
    expect(laid.edges).toHaveLength(4);
  });

  it("draws every edge along the route dagre computed for it", () => {
    // dagre routes while it lays out, around whatever lies between the ends.
    // Hand-picked lanes are what put two rank-skipping edges on top of each
    // other; the only edge that still needs one is the loop, which dagre never
    // saw.
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
    // The return is left out of the dagre graph on purpose -- see layoutGraph --
    // so it has no computed route and takes the one lane that does not cut back
    // through every step it is returning past.
    const laid = layoutGraph(LOOP);
    const loop = laid.edges.find((e) => e.id === "analyse->plan")!;

    // Still the custom edge, which falls back to a step path when it has no
    // points. It was the built-in `smoothstep`, and that could not draw the word
    // on the line -- which the loop needs more than any other edge, being the one
    // that runs against the way the drawing is laid out.
    expect(loop).toMatchObject({ type: "routed", sourceHandle: "right-out", targetHandle: "right-in" });
    expect((loop.data as { points?: unknown }).points).toBeUndefined();
    expect(loop.className).toContain("is-loop");
  });

  it("names every edge that a router picks, and the one that returns", () => {
    // The dash pattern these used to carry meant nothing without a legend, and
    // the legend cost two lines of a pane with 334px to draw in.
    const laid = layoutGraph(LOOP);
    const label = (id: string) => (laid.edges.find((e) => e.id === id)!.data as { label?: string }).label;

    expect(label("analyse->plan")).toBe("되돌아가기");
    // Conditional, but this shape names no router, so the pill says only that a
    // choice is made here. Better than a dash nobody can read.
    expect(label("plan->context")).toBe("조건");
    // Unconditional: there is no choice, so there is nothing to name.
    expect(label("context->analyse")).toBeUndefined();
  });

  it("uses the router's own name when the graph gives one", () => {
    // `plan` is picked by `has_work` on the real graph, and naming it is what
    // makes the edge self-explanatory rather than merely marked.
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
    // `plan -> analyse` crosses `context`. Every bend of its route has to clear
    // the nodes in between, which is what dagre's dummy nodes are for.
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
    // Before and after are separate: stopping on the way in and stopping once
    // it has written answer different questions.
    expect(data.get("context")).toMatchObject({ queued: true, before: true, after: false });
  });
});

describe("the specialists, as one node", () => {
  /**
   * Five boxes that differ only in which flaw they look for were the widest rank
   * on the drawing and owned ten of its twenty-three edges -- every one of them
   * fanning out of one node and back into one node. That is the tangle.
   */
  it("collapses them, and the fan with them", () => {
    const laid = layoutGraph(LENSES);
    const ids = laid.nodes.map((n) => n.id).sort();

    expect(ids).toEqual(["lens:*", "locate", "scout"]);
    // One out of `scout` and one into `locate`, instead of three and three.
    expect(laid.edges.map((e) => e.id).sort()).toEqual(["lens:*->locate", "scout->lens:*"]);
  });

  it("says what it stands in for", () => {
    const group = layoutGraph(LENSES).nodes.find((n) => n.id === "lens:*")!;

    expect(group.data.members).toEqual(["memory", "injection", "crypto"]);
    expect(group.data.label).toBe("전문가 분석");
  });

  it("adds up the run across all of them", () => {
    // `1×` on a box standing in for three that ran twice each is a smaller lie
    // than no number, and still a lie.
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
    // The whole reason the group is allowed to hide four names: when a trail runs
    // through one of them, that one is the answer and it is said on the box.
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
    // Collapsing one node into a group of one is a box that says `렌즈 1`.
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
