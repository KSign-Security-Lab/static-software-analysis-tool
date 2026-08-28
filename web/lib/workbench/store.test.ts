import { describe, expect, it } from "vitest";

import { createWorkbenchStore } from "./store";

/**
 * A panel handle that behaves like the real one.
 *
 * `react-resizable-panels` commits a layout change synchronously -- `j()` does
 * `F.set(group, layout)` before returning -- so `isCollapsed()` immediately after
 * `collapse()` already reports the new state. The mirror in this store was written
 * as `!handle.isCollapsed()` *after* the mutation, which is therefore the opposite
 * of the truth every single time.
 *
 * It looked fine because the panel's own `onResize` fired a moment later and
 * corrected it. That correction is a ResizeObserver notification, and a browser
 * that drops one -- "ResizeObserver loop completed with undelivered notifications"
 * -- leaves the fold button lit backwards with nothing to fix it.
 */
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
    // The whole point: correctness cannot depend on `onResize`, because that is a
    // ResizeObserver callback and browsers drop them under a loop.
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
    // A drag to zero folds a panel without going through this, so the mirror can be
    // stale on the way in. Already folded, so the toggle expands it.
    const store = createWorkbenchStore({ collapsed: { side: false } });
    const panel = fakePanel(true);
    store.getState().registerPanel("side", panel as never);

    store.getState().togglePane("side");
    expect(panel.isCollapsed()).toBe(false);
    expect(store.getState().collapsed.side).toBe(false);
  });

  it("follows the panel when a drag folds it behind our back", () => {
    // `onResize` is where a drag is reported, and it is the one thing that still
    // has to come through a notification -- there is no other way to hear about a
    // pointer. It only ever writes what the panel already is.
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
