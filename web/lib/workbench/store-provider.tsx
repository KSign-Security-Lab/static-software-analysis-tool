"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import { useStore } from "zustand";

import { createWorkbenchStore, type WorkbenchInit, type WorkbenchState, type WorkbenchStore } from "./store";

const WorkbenchContext = createContext<WorkbenchStore | null>(null);

export function WorkbenchStoreProvider({ init, children }: { init?: WorkbenchInit; children: ReactNode }) {
  const [store] = useState<WorkbenchStore>(() => createWorkbenchStore(init));
  return <WorkbenchContext.Provider value={store}>{children}</WorkbenchContext.Provider>;
}

export function useWorkbench<T>(selector: (state: WorkbenchState) => T): T {
  const store = useContext(WorkbenchContext);
  if (!store) throw new Error("useWorkbench must be used inside <WorkbenchStoreProvider>");
  return useStore(store, selector);
}
