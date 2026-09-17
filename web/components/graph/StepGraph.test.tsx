import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { GraphShape } from "@/lib/api/types";
import StepGraph from "./StepGraph";

afterEach(cleanup);

vi.mock("@xyflow/react", () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => <div data-testid="flow">{children}</div>,
  ReactFlowProvider: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  useReactFlow: () => ({ fitView: vi.fn() }),
  Background: () => null,
  BackgroundVariant: { Dots: "dots" },
  Controls: () => null,
  BaseEdge: () => null,
  EdgeLabelRenderer: ({ children }: { children?: React.ReactNode }) => <>{children}</>,
  getSmoothStepPath: () => ["M0,0", 0, 0],
  Handle: () => null,
  Position: { Left: "left", Right: "right", Top: "top", Bottom: "bottom" },
  MarkerType: { ArrowClosed: "arrowclosed" },
}));

const SHAPE: GraphShape = {
  nodes: ["__start__", "plan", "__end__"],
  edges: [
    { source: "__start__", target: "plan", conditional: false },
    { source: "plan", target: "__end__", conditional: true },
  ],
  mermaid: "",
  steppable: ["plan"],
  node_notes: [],
  steps: [],
};

const draw = () =>
  render(
    <StepGraph
      shape={SHAPE}
      spans={[]}
      running={[]}
      queued={[]}
      breakpoints={{ before: [], after: [] }}
      selected={null}
      onSelect={vi.fn()}
      onInterrupt={vi.fn()}
    />,
  );

describe("a canvas whose box has not been measured", () => {
  it("does not mount React Flow", () => {
    draw();
    expect(screen.queryByTestId("flow")).toBeNull();
  });

  it("still renders the box, so something can measure it", () => {
    const { container } = draw();
    expect(container.querySelector("div.absolute.inset-0")).toBeTruthy();
  });

  it("takes its size from a positioned ancestor, not a percentage", () => {
    const { container } = draw();
    const box = container.firstElementChild as HTMLElement;
    expect(box.className).toContain("absolute");
    expect(box.className).not.toContain("h-full");
  });
});

describe("a canvas whose box has a size", () => {
  it("mounts React Flow", async () => {
    const rect = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockReturnValue({ width: 800, height: 600 } as DOMRect);

    draw();
    await waitFor(() => expect(screen.getByTestId("flow")).toBeTruthy());
    rect.mockRestore();
  });
});
