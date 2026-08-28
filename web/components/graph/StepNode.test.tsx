import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type GraphNodeData } from "@/lib/trace/layout";
import StepNode from "./StepNode";

/**
 * What a node on the agent's graph says about itself.
 *
 * The reason this file exists: the drawing said `10 tools` and never which,
 * so there was no way to learn from it that the run can search semantically --
 * and somebody went looking for a `RAG` box that could not exist, because a
 * tool is not a step. Nothing covered the box's output at all before this.
 *
 * Rewritten when the box became a puck with its label beside it. Two of the
 * facts it used to assert are now carried by shape rather than by words -- see
 * the note on the puck in StepNode -- so they are asserted as shape here. The
 * facts themselves did not change, and that is the point of keeping the file.
 */

afterEach(cleanup);

vi.mock("@xyflow/react", () => ({
  // Ports are all this needs from React Flow, and they render nothing visible.
  Handle: () => null,
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
}));

const TOOLS = ["read_source", "search_text", "search_semantic", "find_callers"];

function data(over: Partial<GraphNodeData> = {}): GraphNodeData {
  return {
    name: "gather",
    label: "근거 수집",
    terminal: false,
    visits: 0,
    averageMs: null,
    running: 0,
    queued: false,
    before: false,
    after: false,
    steps: ["gather"],
    tools: TOOLS.length,
    roster: true,
    across: true,
    ...over,
  };
}

// React Flow hands a node a dozen props it computes itself; only these two are
// read here, and standing the rest up would be a fixture about React Flow.
const draw = (over: Partial<GraphNodeData> = {}) =>
  render(
    <StepNode {...({ data: data(over), selected: false } as unknown as React.ComponentProps<typeof StepNode>)} />,
  );

/** The disc or square carrying the node's icon and its state. */
const puck = (over: Partial<GraphNodeData> = {}) =>
  draw(over).container.querySelector("span.size-10")?.className ?? "";

describe("what a node is called", () => {
  it("leads with what it does, in the reader's language", () => {
    draw();
    expect(screen.getByText("근거 수집")).toBeTruthy();
  });

  it("keeps its machine name, because everything else refers to it that way", () => {
    // Breakpoints, spans and errors all say `gather`. A drawing that only spoke
    // Korean could not be found from any of them.
    draw();
    expect(screen.getByText(/gather/)).toBeTruthy();
  });
});

describe("a node that holds tools", () => {
  it("still says how many, because the list may be capped", () => {
    draw();
    expect(screen.getByText(/도구 4/)).toBeTruthy();
  });

  it("says nothing about tools when it has none", () => {
    draw({ name: "locate", label: "위치 찾기", steps: [], tools: 0 });
    expect(screen.queryByText(/도구/)).toBeNull();
  });
});

describe("agent against plain code", () => {
  /**
   * Half the graph is deterministic Python and nothing said so, which is the
   * fix this asserts. The word `agent` used to be in the box; the label lives
   * outside the shape now and does not fit, so the shape carries it -- round is
   * an agent, square is code.
   */
  it("draws a node that calls a model as a disc", () => {
    expect(puck()).toContain("rounded-full");
  });

  it("draws a node that calls none as a square", () => {
    expect(puck({ name: "locate", label: "위치 찾기", steps: [], tools: 0 })).toContain("rounded-md");
  });

  it("does not claim either until the roster has arrived", () => {
    // Calling every node code because the answer had not come back would be a
    // lie rather than a gap, so an unknown node takes the quiet shape and none
    // of the agent's own emphasis.
    expect(puck({ roster: false })).not.toContain("bg-surface-3");
  });
});

describe("a node outside the argument being read", () => {
  /**
   * With a finding open, the drawing marks the agents that produced it and dims
   * the rest -- the graph's answer to "how was each agent involved in this
   * decision". Both halves are asserted: dimming alone was invisible unless you
   * already knew to look, so the trail is drawn in accent as well.
   */
  const outer = (over: Partial<GraphNodeData>) =>
    draw(over).container.querySelector("div.group\\/node")?.className ?? "";

  it("is dimmed, not hidden", () => {
    // A node that did not run is part of the answer too: `skip` staying visible
    // is how you see that the unit was not skipped.
    expect(outer({ faded: true })).toContain("opacity-45");
  });

  it("is at full strength when it is on the path", () => {
    expect(outer({ lit: true })).not.toContain("opacity-45");
  });

  it("is at full strength when nothing is narrowing the drawing", () => {
    // `faded` is unset unless a finding is open, so the ordinary case is untouched.
    expect(outer({})).not.toContain("opacity-45");
  });

  it("marks the ones on the path rather than only dimming the others", () => {
    expect(puck({ lit: true })).toContain("ring-accent");
  });

  it("still says what it is while dimmed", () => {
    draw({ faded: true });
    expect(screen.getByText("근거 수집")).toBeTruthy();
    expect(screen.getByText(/도구 4/)).toBeTruthy();
  });
});

describe("a node with a run on it", () => {
  it("counts a wave rather than saying one thing is running", () => {
    draw({ running: 4 });
    expect(screen.getByText("4 실행")).toBeTruthy();
  });

  it("says how many times it has been entered once it is done", () => {
    draw({ visits: 3, averageMs: 1280 });
    expect(screen.getByText("3×")).toBeTruthy();
    expect(screen.getByText(/1\.3s/)).toBeTruthy();
  });
});
