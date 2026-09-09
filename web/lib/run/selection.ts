"use client";

import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useCallback, useMemo } from "react";

export function useSelectedFinding() {
  return useQueryState("finding", parseAsString.withOptions({ history: "replace" }));
}

export const SORTS = ["severity", "file", "confidence"] as const;
export type Sort = (typeof SORTS)[number];

export function useSort() {
  return useQueryState(
    "sort",
    parseAsStringLiteral(SORTS).withDefault("severity").withOptions({ history: "replace" }),
  );
}

export type Selection = { kind: "finding"; id: string } | { kind: "call"; id: string } | null;

export type SelectionKind = NonNullable<Selection>["kind"];

export interface SelectionState {
  selection: Selection;
  select: (next: Selection) => void;
  clear: () => void;
}

export function useSelection(): SelectionState {
  const [finding, setFinding] = useSelectedFinding();
  const [call, setCall] = useQueryState("span", parseAsString.withOptions({ history: "replace" }));

  const selection = useMemo<Selection>(() => {
    if (call) return { kind: "call", id: call };
    if (finding) return { kind: "finding", id: finding };
    return null;
  }, [finding, call]);

  const select = useCallback(
    (next: Selection) => {
      if (next?.kind === "call") {
        void setCall(next.id);
        return;
      }
      void setCall(null);
      void setFinding(next?.kind === "finding" ? next.id : null);
    },
    [setFinding, setCall],
  );

  const clear = useCallback(() => select(null), [select]);

  return { selection, select, clear };
}

export function idOf(selection: Selection, kind: SelectionKind): string | null {
  return selection?.kind === kind ? selection.id : null;
}
