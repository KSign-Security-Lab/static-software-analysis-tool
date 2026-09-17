import type { PanelImperativeHandle } from "react-resizable-panels";
import { createStore } from "zustand/vanilla";

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
      const folding = !handle.isCollapsed();
      if (folding) handle.collapse();
      else handle.expand();
      get().setCollapsed(id, folding);
    },

    isFolded: (id) => panels.get(id)?.isCollapsed() ?? get().collapsed[id],
  }));
}
