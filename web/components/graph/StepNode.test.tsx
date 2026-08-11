import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NODE_H, NODE_W, heightOf, widthOf, type GraphNodeData } from "@/lib/trace/layout";
import StepNode from "./StepNode";

/**
 * What a box on the agent's graph says about itself.
 *
 * The reason this file exists: the drawing said `10 tools` and never which,
 * so there was no way to learn from it that the run can search semantically --
 * and somebody went looking for a `RAG` box that could not exist, because a
 * tool is not a step. Nothing covered the box's output at all before this.
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
    terminal: false,
    visits: 0,
    averageMs: null,
    running: 0,
    queued: false,
    before: false,
    after: false,
    steps: ["gather"],
    tools: TOOLS.length,
    toolNames: TOOLS,
    height: heightOf(TOOLS),
    width: widthOf(TOOLS),
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

describe("a node that holds tools", () => {
  it("names them, so semantic search is findable without clicking anything", () => {
    draw();
    for (const tool of TOOLS) expect(screen.getByText(tool)).toBeTruthy();
  });

  it("still says how many, because the list may be capped", () => {
    draw();
    expect(screen.getByText("4 tools")).toBeTruthy();
  });

  it("is taller than a node that holds none", () => {
    expect(heightOf(TOOLS)).toBeGreaterThan(NODE_H);
    expect(heightOf([])).toBe(NODE_H);
  });

  it("is wide enough for its longest name, so none of them ends in an ellipsis", () => {
    // A truncated `search_seman…` is most of the way back to the count it
    // replaced, which is the thing this change exists to remove.
    expect(widthOf(TOOLS)).toBeGreaterThan(NODE_W);
    expect(widthOf(["graph_neighbours"])).toBeGreaterThan(widthOf(["read_source"]));
    expect(widthOf([])).toBe(NODE_W);
  });

  it("truncates rather than growing to the height of the canvas", () => {
    const many = Array.from({ length: 20 }, (_, index) => `tool_${index}`);
    draw({ toolNames: many, tools: many.length, height: heightOf(many), width: widthOf(many) });

    expect(screen.getByText("… +8")).toBeTruthy();
    expect(screen.queryByText("tool_19")).toBeNull();
    expect(heightOf(many)).toBe(heightOf(many.slice(0, 12).concat("x")));
  });
});

describe("a node that holds none", () => {
  it("shows no list and keeps the ordinary height", () => {
    draw({ name: "locate", steps: [], tools: 0, toolNames: [], height: NODE_H, width: NODE_W });

    expect(screen.queryByText("read_source")).toBeNull();
    expect(screen.queryByRole("list")).toBeNull();
    expect(screen.getByText("code")).toBeTruthy();
  });

  it("says nothing at all until the roster has arrived", () => {
    // Tagging every node `code` because the answer had not come back would be a
    // lie rather than a gap.
    draw({ roster: false });
    expect(screen.queryByText("agent")).toBeNull();
    expect(screen.queryByText("read_source")).toBeNull();
  });
});
