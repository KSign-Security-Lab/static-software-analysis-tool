import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { GraphShape } from "@/lib/api/types";
import StepGraph from "./StepGraph";

/**
 * The canvas must not draw into a box it has not measured.
 *
 * This file exists because of a bug that shipped three times. React Flow
 * measures its container on mount and refuses to lay anything out without one:
 * "[React Flow]: The parent container needs a width and a height to render the
 * graph" (error #004), and a blank canvas with no other symptom.
 *
 * The container had no size on the first paint. Every ancestor between the
 * window and the canvas sized itself from something it had to measure first,
 * and the last of them -- `PanelShell`'s body -- is `min-h-0 flex-1`, which has
 * no *definite* height for a percentage child to resolve against.
 *
 * It was missed by every check because the checks screenshotted five seconds
 * after load, by which time the ResizeObserver had fired and the box was real.
 * A settled screenshot cannot see a broken first frame. jsdom reports every
 * element as 0x0, so this file is that first frame, permanently.
 */

afterEach(cleanup);

// The canvas itself is React Flow's; what is under test is whether we hand it a
// box. A stub records the fact of being rendered without dragging a WebGL-free
// layout engine into jsdom.
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
    // jsdom gives every element a zero rect, which is exactly the state the
    // real page is in on the frame the dialog opens.
    draw();
    expect(screen.queryByTestId("flow")).toBeNull();
  });

  it("still renders the box, so something can measure it", () => {
    // Waiting for a size it never asked for would be a canvas that never
    // appears -- the observer needs an element to observe.
    const { container } = draw();
    expect(container.querySelector("div.absolute.inset-0")).toBeTruthy();
  });

  it("takes its size from a positioned ancestor, not a percentage", () => {
    // `h-full` here is a percentage of `PanelShell`'s body, which is
    // `min-h-0 flex-1` and has no definite height to be a percentage of.
    const { container } = draw();
    const box = container.firstElementChild as HTMLElement;
    expect(box.className).toContain("absolute");
    expect(box.className).not.toContain("h-full");
  });
});

describe("a canvas whose box has a size", () => {
  it("mounts React Flow", async () => {
    // What the browser does once layout has run.
    const rect = vi
      .spyOn(HTMLElement.prototype, "getBoundingClientRect")
      .mockReturnValue({ width: 800, height: 600 } as DOMRect);

    draw();
    await waitFor(() => expect(screen.getByTestId("flow")).toBeTruthy());
    rect.mockRestore();
  });
});
