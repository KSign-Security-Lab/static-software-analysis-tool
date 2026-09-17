import { describe, expect, it } from "vitest";

import { createWorkbenchStore } from "./store";

function fakePanel(collapsed = false) {
  let isCollapsed = collapsed;
  return {
    collapse: () => {
      isCollapsed = true;
    },
    expand: () => {
      isCollapsed = false;
    },
    isCollapsed: () => isCollapsed,
    getSize: () => ({ asPercentage: isCollapsed ? 0 : 30, inPixels: isCollapsed ? 0 : 300 }),
    resize: () => {},
  };
}

describe("togglePane", () => {
  it("records the fold it just performed, not its opposite", () => {
    const store = createWorkbenchStore();
    const panel = fakePanel();
    store.getState().registerPanel("inspector", panel as never);

    store.getState().togglePane("inspector");
    expect(panel.isCollapsed()).toBe(true);
    expect(store.getState().collapsed.inspector).toBe(true);

    store.getState().togglePane("inspector");
    expect(panel.isCollapsed()).toBe(false);
    expect(store.getState().collapsed.inspector).toBe(false);
  });

  it("stays right without any resize notification arriving", () => {
    const store = createWorkbenchStore({ collapsed: { dock: false } });
    const panel = fakePanel();
    store.getState().registerPanel("dock", panel as never);

    for (const expected of [true, false, true]) {
      store.getState().togglePane("dock");
      expect(store.getState().collapsed.dock).toBe(expected);
      expect(store.getState().isFolded("dock")).toBe(expected);
    }
  });

  it("asks the panel rather than the mirror, so a drag to zero is respected", () => {
    const store = createWorkbenchStore({ collapsed: { side: false } });
    const panel = fakePanel(true);
    store.getState().registerPanel("side", panel as never);

    store.getState().togglePane("side");
    expect(panel.isCollapsed()).toBe(false);
    expect(store.getState().collapsed.side).toBe(false);
  });

  it("follows the panel when a drag folds it behind our back", () => {
    const store = createWorkbenchStore();
    store.getState().setCollapsed("inspector", true);
    expect(store.getState().collapsed.inspector).toBe(true);
  });

  it("does nothing when no panel is registered", () => {
    const store = createWorkbenchStore();
    store.getState().togglePane("inspector");
    expect(store.getState().collapsed.inspector).toBe(false);
  });
});
