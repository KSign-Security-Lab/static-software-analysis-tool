import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { type GraphNodeData } from "@/lib/trace/layout";
import StepNode from "./StepNode";

afterEach(cleanup);

vi.mock("@xyflow/react", () => ({
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

const draw = (over: Partial<GraphNodeData> = {}) =>
  render(
    <StepNode {...({ data: data(over), selected: false } as unknown as React.ComponentProps<typeof StepNode>)} />,
  );

const puck = (over: Partial<GraphNodeData> = {}) =>
  draw(over).container.querySelector("span.size-10")?.className ?? "";

describe("what a node is called", () => {
  it("leads with what it does, in the reader's language", () => {
    draw();
    expect(screen.getByText("근거 수집")).toBeTruthy();
  });

  it("keeps its machine name, because everything else refers to it that way", () => {
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
  it("draws a node that calls a model as a disc", () => {
    expect(puck()).toContain("rounded-full");
  });

  it("draws a node that calls none as a square", () => {
    expect(puck({ name: "locate", label: "위치 찾기", steps: [], tools: 0 })).toContain("rounded-md");
  });

  it("does not claim either until the roster has arrived", () => {
    expect(puck({ roster: false })).not.toContain("bg-surface-3");
  });
});

describe("a node outside the argument being read", () => {
  const outer = (over: Partial<GraphNodeData>) =>
    draw(over).container.querySelector("div.group\\/node")?.className ?? "";

  it("is dimmed, not hidden", () => {
    expect(outer({ faded: true })).toContain("opacity-45");
  });

  it("is at full strength when it is on the path", () => {
    expect(outer({ lit: true })).not.toContain("opacity-45");
  });

  it("is at full strength when nothing is narrowing the drawing", () => {
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
