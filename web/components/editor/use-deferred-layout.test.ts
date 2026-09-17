import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useDeferredLayout } from "./use-deferred-layout";

let frames: Array<() => void>;
let observed: Array<() => void>;

function runFrame() {
  const due = frames;
  frames = [];
  for (const frame of due) frame();
}

beforeEach(() => {
  frames = [];
  observed = [];
  vi.stubGlobal("requestAnimationFrame", (callback: () => void) => {
    frames.push(callback);
    return frames.length;
  });
  vi.stubGlobal("cancelAnimationFrame", () => {});
  vi.stubGlobal(
    "ResizeObserver",
    class {
      constructor(callback: () => void) {
        observed.push(callback);
      }
      observe() {}
      disconnect() {}
    },
  );
});

afterEach(() => vi.unstubAllGlobals());

describe("useDeferredLayout", () => {
  it("lays out when asked, with no resize to prompt it", () => {
    const layout = vi.fn();
    const { result } = renderHook(() => useDeferredLayout(layout));

    result.current.relayout();
    expect(layout).not.toHaveBeenCalled();

    runFrame();
    expect(layout).toHaveBeenCalledOnce();
  });

  it("still lays out on a resize", () => {
    const layout = vi.fn();
    const { result } = renderHook(() => useDeferredLayout(layout));
    result.current.observe(document.createElement("div"));

    observed[0]();
    runFrame();
    expect(layout).toHaveBeenCalledOnce();
  });

  it("coalesces a burst into one layout", () => {
    const layout = vi.fn();
    const { result } = renderHook(() => useDeferredLayout(layout));
    result.current.observe(document.createElement("div"));

    result.current.relayout();
    observed[0]();
    observed[0]();
    runFrame();

    expect(layout).toHaveBeenCalledOnce();
  });

  it("lays out again after the frame has run", () => {
    const layout = vi.fn();
    const { result } = renderHook(() => useDeferredLayout(layout));

    result.current.relayout();
    runFrame();
    result.current.relayout();
    runFrame();

    expect(layout).toHaveBeenCalledTimes(2);
  });

  it("calls the newest layout, not the one it was mounted with", () => {
    const first = vi.fn();
    const second = vi.fn();
    const { result, rerender } = renderHook(({ layout }) => useDeferredLayout(layout), {
      initialProps: { layout: first },
    });

    rerender({ layout: second });
    result.current.relayout();
    runFrame();

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledOnce();
  });
});
