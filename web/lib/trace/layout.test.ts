import { describe, expect, it } from "vitest";

import { backEdges, layoutGraph, statsFromSpans } from "./layout";
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

  it("routes the return up one side and the early exit down the other", () => {
    // Both skip over the column. Drawn through it, the return crosses every
    // node between `analyse` and `plan`, which is what made the first draw of
    // this unreadable.
    const laid = layoutGraph(LOOP);
    const edge = (id: string) => laid.edges.find((e) => e.id === id)!;

    expect(edge("analyse->plan")).toMatchObject({ sourceHandle: "right-out", targetHandle: "right-in" });
    expect(edge("plan->__end__")).toMatchObject({ sourceHandle: "left-out", targetHandle: "left-in" });
    // The steps of the column itself stay on the column.
    expect(edge("plan->context").sourceHandle).toBeUndefined();
    expect(edge("context->analyse").sourceHandle).toBeUndefined();
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
