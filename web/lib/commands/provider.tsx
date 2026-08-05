"use client";

import { createContext, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";

import { CommandRegistry, type Command } from "./registry";

const RegistryContext = createContext<CommandRegistry | null>(null);

export function CommandProvider({ children }: { children: ReactNode }) {
  // Per tab, like the workbench store, and for the same reason: a module-level
  // registry is shared across requests on the Node server.
  const [registry] = useState(() => new CommandRegistry());
  return <RegistryContext.Provider value={registry}>{children}</RegistryContext.Provider>;
}

export function useRegistry(): CommandRegistry {
  const registry = useContext(RegistryContext);
  if (!registry) throw new Error("commands must be used inside <CommandProvider>");
  return registry;
}

/** Everything registered right now, re-rendering when that changes. */
export function useCommandList(): Command[] {
  const registry = useRegistry();
  return useSyncExternalStore(registry.subscribe, registry.getSnapshot, registry.getSnapshot);
}

/**
 * Contribute commands for as long as this component is mounted.
 *
 * `build` is called on every change of `deps`, so a command closing over a
 * selected finding stays correct without the caller thinking about it.
 */
export function useCommands(build: () => Command[], deps: unknown[]): void {
  const registry = useRegistry();
  useEffect(() => {
    return registry.register(build());
    // The caller owns the dependency list; `build` is deliberately not in it,
    // since an inline arrow would re-register on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [registry, ...deps]);
}
