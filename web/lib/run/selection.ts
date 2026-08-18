"use client";

import { parseAsBoolean, parseAsInteger, parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";
import { useCallback, useMemo } from "react";

/**
 * What the inspect surface is looking at, in the URL.
 *
 * `file`, `finding` and `line` are `replace` history: clicking through a list
 * should not fill the back stack with twenty entries. `run` is `push`, and lives
 * in lib/run/use-run-id.ts because the stream needs it too.
 */
export function useOpenFile() {
  return useQueryState("file", parseAsString.withOptions({ history: "replace" }));
}

export function useSelectedFinding() {
  return useQueryState("finding", parseAsString.withOptions({ history: "replace" }));
}

/**
 * Which line the editor should be looking at.
 *
 * Not derivable from `finding`, which is why it is its own param. A finding is
 * a claim about several lines in several files -- the evidence trail walks 유입
 * → 전파 → 위험 지점 and each step is somewhere else -- but the only line the
 * editor ever knew about was the claim's own. Every step in the trail opened
 * the right file and then landed on the wrong line, or on a line in a file the
 * step had nothing to do with.
 *
 * In the URL for the same reason `file` is: it is what you are looking at, and
 * a step in an argument is worth being able to link someone to. `replace`, so
 * walking a five-step trail leaves one back-stack entry rather than five.
 */
export function useRevealLine() {
  return useQueryState("line", parseAsInteger.withOptions({ history: "replace" }));
}

/* -- how much of the run the list shows -------------------------------------- */

export const FILTERS = ["problems", "all", "tools"] as const;
export type Filter = (typeof FILTERS)[number];

/**
 * A filter, not a tab, and the distinction is the whole point: the rows are the
 * same rows.
 *
 * A finding is not a separate artefact from the record -- it *is* the row where a
 * specialist raised it. So 문제 and 기록 were never two places to be; they were
 * one list at two settings, and splitting them across tabs meant reading one
 * finding's reasoning was a round trip between them.
 *
 * `problems` is the default and drops out of the address bar, so a bare link
 * opens on the answer rather than on the machinery.
 */
export function useFilter() {
  return useQueryState(
    "show",
    parseAsStringLiteral(FILTERS).withDefault("problems").withOptions({ history: "replace" }),
  );
}

/**
 * Whether the filter moved by itself, because a scan started.
 *
 * So it can say why. Opening the whole record when a scan begins is wanted -- a
 * run in flight is only legible as it moves -- but a panel that changes under the
 * reader without saying so is the screen rearranging itself for reasons they
 * cannot see.
 */
export function useOpenedByRun() {
  return useQueryState("auto", parseAsBoolean.withDefault(false).withOptions({ history: "replace" }));
}

/**
 * Whether the structure canvas is open over the page.
 *
 * Not part of `Selection` below: that union is the one *thing* being read, and
 * this is where it is being read. They compose rather than compete -- opening
 * the canvas from a finding keeps `?finding=` set, so the drawing lights that
 * finding's trail while the rail still shows its grounds.
 *
 * In the URL because it changes what is on screen, and `replace` because
 * opening and closing a drawing is not somewhere to go back to.
 */
export function useStructureOpen() {
  return useQueryState("graph", parseAsBoolean.withDefault(false).withOptions({ history: "replace" }));
}

/* -- the one selection ------------------------------------------------------- */

/**
 * The one thing the inspector is showing.
 *
 * Three params could be set at once -- `finding`, `span`, `node` -- each
 * written by whichever pane owned it. So nothing on screen could state what the
 * right-hand pane was showing without knowing the precedence its renderer
 * happened to use, and clearing one left the others behind. That is the bug this
 * closes: there is one selection, it has a kind, and setting it clears the others
 * here rather than in five places that must all remember to.
 *
 * The param names are kept. `finding` in particular is shared with F2-A and
 * drives the editor's markers; renaming it would be churn for nothing.
 */
export type Selection =
  | { kind: "finding"; id: string }
  | { kind: "call"; id: string }
  | { kind: "node"; id: string }
  | null;

export type SelectionKind = NonNullable<Selection>["kind"];

export interface SelectionState {
  selection: Selection;
  select: (next: Selection) => void;
  clear: () => void;
}

export function useSelection(): SelectionState {
  const [finding, setFinding] = useSelectedFinding();
  const [call, setCall] = useQueryState("span", parseAsString.withOptions({ history: "replace" }));
  const [node, setNode] = useQueryState("node", parseAsString.withOptions({ history: "replace" }));

  // Precedence exists only for a hand-written URL that sets two of them.
  // Everything the app writes goes through `select`, which cannot produce that.
  const selection = useMemo<Selection>(() => {
    if (finding) return { kind: "finding", id: finding };
    if (call) return { kind: "call", id: call };
    if (node) return { kind: "node", id: node };
    return null;
  }, [finding, call, node]);

  const select = useCallback(
    (next: Selection) => {
      // Every setter every time, so a kind that is not being selected is cleared
      // whether or not this caller knew it existed. That is what makes "exactly
      // one" a property of the hook rather than a convention callers follow.
      void setFinding(next?.kind === "finding" ? next.id : null);
      void setCall(next?.kind === "call" ? next.id : null);
      void setNode(next?.kind === "node" ? next.id : null);
    },
    [setFinding, setCall, setNode],
  );

  const clear = useCallback(() => select(null), [select]);

  return { selection, select, clear };
}

/** The selected id when it is of this kind, else null -- for a pane that wants one. */
export function idOf(selection: Selection, kind: SelectionKind): string | null {
  return selection?.kind === kind ? selection.id : null;
}
