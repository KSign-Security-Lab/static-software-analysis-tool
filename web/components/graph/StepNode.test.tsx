import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type GraphNodeData } from "@/lib/trace/layout";
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

  it("still says how many, because the list may be capped", () => {
    draw();
    expect(screen.getByText("4 tools")).toBeTruthy();
  });



});

describe("a node that holds none", () => {
  it("says it is code rather than an agent", () => {
    draw({ name: "locate", steps: [], tools: 0 });

    expect(screen.getByText("code")).toBeTruthy();
  });

  it("says nothing at all until the roster has arrived", () => {
    // Tagging every node `code` because the answer had not come back would be a
    // lie rather than a gap.
    draw({ roster: false });
    expect(screen.queryByText("agent")).toBeNull();
    expect(screen.queryByText("4 tools")).toBeNull();
  });
});

describe("a node outside the argument being read", () => {
  /**
   * With a finding open, the drawing marks the agents that produced it and dims
   * the rest -- which is the graph's answer to "how was each agent involved in
   * this decision". Dimming rather than highlighting because a node already
   * carries five states, and a sixth colour competing with those is a legend
   * nobody can hold.
   */
  const opacity = (over: Partial<GraphNodeData>) => {
    const { container } = draw(over);
    // The card is the element carrying the box's own border and background.
    return container.querySelector("div.rounded-md")?.className ?? "";
  };

  it("is dimmed, not hidden", () => {
    // A node that did not run is part of the answer too: `skip` staying visible
    // is how you see that the unit was not skipped.
    expect(opacity({ faded: true })).toContain("opacity-30");
  });

  it("is at full strength when it is on the path", () => {
    expect(opacity({ faded: false })).not.toContain("opacity-30");
  });

  it("is at full strength when nothing is narrowing the drawing", () => {
    // `faded` is unset unless a finding is open, so the ordinary case is untouched.
    expect(opacity({})).not.toContain("opacity-30");
  });

  it("still says what it is while dimmed", () => {
    draw({ faded: true });
    expect(screen.getByText("gather")).toBeTruthy();
    expect(screen.getByText("4 tools")).toBeTruthy();
  });
});
