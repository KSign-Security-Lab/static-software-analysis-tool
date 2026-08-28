import type { PanelImperativeHandle } from "react-resizable-panels";
import { createStore } from "zustand/vanilla";

/**
 * Workbench UI state: which panels are folded.
 *
 * The chosen dock tab used to live here too, so the shell could read it. The shell
 * never did -- one surface's tab strip is nobody else's business -- and it is
 * component state in DockTabs now.
 *
 * Not context, because `onResize` fires on every animation frame of a drag and
 * a single context value re-renders every consumer at that rate; a selector
 * subscription re-renders only what read the slice that changed.
 *
 * Not a module singleton either -- see store-provider.tsx.
 *
 * This store observes the geometry, it never drives it. The panel handles are
 * the source of truth for whether something is folded; `collapsed` is a mirror
 * kept so the activity bar can render a dot and the status bar can label a
 * toggle. Two sources of truth for the same fold is how the old studio ended
 * up with a fold flag and a flex-basis fighting each other.
 */

export type PaneId = "side" | "dock" | "inspector";

export const PANE_LABEL: Record<PaneId, string> = {
  side: "탐색기",
  dock: "하단 패널",
  inspector: "인스펙터",
};

export interface WorkbenchState {
  collapsed: Record<PaneId, boolean>;
  setCollapsed: (id: PaneId, value: boolean) => void;
  registerPanel: (id: PaneId, handle: PanelImperativeHandle | null) => void;
  togglePane: (id: PaneId) => void;
  isFolded: (id: PaneId) => boolean;
}

export interface WorkbenchInit {
  collapsed?: Partial<Record<PaneId, boolean>>;
}

export type WorkbenchStore = ReturnType<typeof createWorkbenchStore>;

export function createWorkbenchStore(init: WorkbenchInit = {}) {
  // Outside the store: handles are mutable imperative objects, not state, and
  // putting them in it would publish a change to every subscriber on mount.
  const panels = new Map<PaneId, PanelImperativeHandle>();

  return createStore<WorkbenchState>()((set, get) => ({
    collapsed: { side: false, dock: false, inspector: false, ...init.collapsed },

    setCollapsed: (id, value) =>
      set((state) => (state.collapsed[id] === value ? state : { collapsed: { ...state.collapsed, [id]: value } })),

    registerPanel: (id, handle) => {
      if (handle) panels.set(id, handle);
      else panels.delete(id);
    },

    togglePane: (id) => {
      const handle = panels.get(id);
      if (!handle) return;
      // Ask the panel, do not trust the mirror: a drag to zero folds it without
      // anything here being told first.
      //
      // Then decide the target *before* mutating, and record that. Reading
      // `handle.isCollapsed()` afterwards recorded the opposite of the truth every
      // time: the library commits a layout change synchronously -- `j()` does
      // `F.set(group, layout)` before returning -- so by then the handle already
      // reports the new state, and negating it inverts it.
      //
      // It looked fine because `onResize` fired a moment later and corrected it.
      // That is a ResizeObserver callback, and a browser that drops one under a
      // loop -- "ResizeObserver loop completed with undelivered notifications" --
      // left the fold button lit backwards with nothing to put it right. Nothing
      // here depends on a notification arriving any more.
      const folding = !handle.isCollapsed();
      if (folding) handle.collapse();
      else handle.expand();
      get().setCollapsed(id, folding);
    },

    isFolded: (id) => panels.get(id)?.isCollapsed() ?? get().collapsed[id],
  }));
}
