"use client";

import { useQueryState } from "nuqs";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { perspectiveFor } from "@/lib/workbench/perspectives";
import { clearRestored, markRestored, readSessionRun, wasRestored, writeSessionRun } from "./session";

function wantsRun(pathname: string): boolean {
  return perspectiveFor(pathname)?.carries.includes("run") ?? false;
}

export interface RunIdState {
  runId: string | null;
  setRunId: (id: string | null) => void;
  restored: boolean;
}

export function useRunState(): RunIdState {
  const pathname = usePathname();
  const [runId, setQueryRunId] = useQueryState("run", { history: "push" });

  const wanted = wantsRun(pathname);

  useEffect(() => {
    if (runId) {
      if (wanted) writeSessionRun(runId);
      return;
    }
    if (!wanted) return;
    const remembered = readSessionRun();
    if (remembered) {
      markRestored();
      void setQueryRunId(remembered, { history: "replace" });
    }
  }, [runId, wanted, setQueryRunId]);

  return {
    runId,
    restored: wasRestored() && Boolean(runId),
    setRunId: (id) => {
      clearRestored();
      if (id === null) writeSessionRun(null);
      void setQueryRunId(id);
    },
  };
}

export function useRunId(): [string | null, (id: string | null) => void] {
  const { runId, setRunId } = useRunState();
  return [runId, setRunId];
}
