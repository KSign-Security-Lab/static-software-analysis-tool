"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { useStore } from "zustand";

import { createWorkbenchStore, type WorkbenchInit, type WorkbenchState, type WorkbenchStore } from "./store";

const WorkbenchContext = createContext<WorkbenchStore | null>(null);

/**
 * One store per request, never a module-level singleton.
 *
 * A singleton is shared across requests on the Node server, so one user's
 * folded panels would render into another user's HTML. The bug only shows
 * under concurrent traffic, which is exactly when nobody is looking.
 */
export function WorkbenchStoreProvider({ init, children }: { init?: WorkbenchInit; children: ReactNode }) {
  // A lazy useState rather than the usual `ref.current ??=`: reading a ref
  // during render is what the React Compiler rules now forbid, and this says
  // the same thing -- built once, never replaced -- without the escape hatch.
  const [store] = useState<WorkbenchStore>(() => createWorkbenchStore(init));
  return <WorkbenchContext.Provider value={store}>{children}</WorkbenchContext.Provider>;
}

export function useWorkbench<T>(selector: (state: WorkbenchState) => T): T {
  const store = useContext(WorkbenchContext);
  if (!store) throw new Error("useWorkbench must be used inside <WorkbenchStoreProvider>");
  return useStore(store, selector);
}
