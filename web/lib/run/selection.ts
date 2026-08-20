"use client";

import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useCallback, useMemo } from "react";

/**
 * What 검사 is looking at, in the URL.
 *
 * Two things only: which finding is open, and which recorded call inside its
 * 판단 과정 is open. Both are `replace` history -- working down a list of forty
 * findings should not put forty entries in the back stack. `run` is `push`, and
 * lives in lib/run/use-run-id.ts because the stream needs it too.
 *
 * `file` and `line` are gone with the editor. They existed to point one at a
 * line; there is no editor to point, and a finding now carries its own excerpt.
 */

export function useSelectedFinding() {
  return useQueryState("finding", parseAsString.withOptions({ history: "replace" }));
}

/* -- how the list is ordered ------------------------------------------------- */

export const SORTS = ["severity", "file", "confidence"] as const;
export type Sort = (typeof SORTS)[number];

/**
 * Row order, in the URL.
 *
 * `severity` is the default and drops out of the address bar, so a bare link
 * opens on the worst thing found. The other two are real questions -- "what is
 * wrong in this file" and "what is it most sure of" -- and worth being able to
 * send someone.
 */
export function useSort() {
  return useQueryState(
    "sort",
    parseAsStringLiteral(SORTS).withDefault("severity").withOptions({ history: "replace" }),
  );
}

/* -- the one selection ------------------------------------------------------- */

/**
 * The one thing the detail column is showing.
 *
 * Two params could be set at once -- `finding` and `span` -- each written by
 * whichever pane owned it, so nothing on screen could state what was being shown
 * without knowing the precedence its renderer happened to use, and clearing one
 * left the other behind. There is one selection, it has a kind, and setting it
 * clears the others here rather than in the places that must all remember to.
 *
 * A call is a *part of* the open finding rather than an alternative to it -- the
 * step of 판단 과정 being read -- so `select`ing one keeps `?finding=` set. That
 * is the one case where two params are legitimately live at once, which is why
 * the kinds are ordered the way they are below.
 */
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

  // A call is the narrower reading, so it wins when both are set.
  const selection = useMemo<Selection>(() => {
    if (call) return { kind: "call", id: call };
    if (finding) return { kind: "finding", id: finding };
    return null;
  }, [finding, call]);

  const select = useCallback(
    (next: Selection) => {
      if (next?.kind === "call") {
        // Deliberately does not touch `finding`: the call belongs to it.
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

/** The selected id when it is of this kind, else null -- for a pane that wants one. */
export function idOf(selection: Selection, kind: SelectionKind): string | null {
  return selection?.kind === kind ? selection.id : null;
}
