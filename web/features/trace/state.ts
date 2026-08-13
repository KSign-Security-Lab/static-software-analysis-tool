"use client";

import { parseAsBoolean, parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";

/**
 * What the trace is looking at, in the URL.
 *
 * All new. Trace selection used to be component state, so "look at this call"
 * was not a thing you could send anyone -- which is most of the value of the
 * view existing at all.
 */
/** Narrows 진행 to one node of the graph -- what clicking a node means. */
export function useScopedNode() {
  return useQueryState("node", parseAsString.withOptions({ history: "replace" }));
}

export function useSelectedSpan() {
  return useQueryState("span", parseAsString.withOptions({ history: "replace" }));
}

export function useSelectedCheckpoint() {
  return useQueryState("cp", parseAsString.withOptions({ history: "replace" }));
}

/**
 * Whether the state panel asks for whole values.
 *
 * Not cosmetic: it changes the request, because without it the server
 * summarises the bulky channels to a count.
 */
export function useFullState() {
  return useQueryState("fullstate", parseAsBoolean.withDefault(false).withOptions({ history: "replace" }));
}

/**
 * What the right pane is showing.
 *
 * The pane answers three questions and they want different amounts of the same
 * material, so which one you are asking is a mode rather than a scroll position.
 *
 * `log` is the default and deliberately so: the pane's first job is to be the
 * record, and a record that opens folded asks you to guess where to click before
 * it has told you anything.
 *
 * In the address bar with everything else that scopes this page -- the run, the
 * node, the finding -- so a link to what you are looking at is a link to what you
 * are looking at.
 */
export const PANE_MODES = ["log", "map", "tools"] as const;
export type PaneMode = (typeof PANE_MODES)[number];

export function usePaneMode() {
  return useQueryState(
    "pane",
    parseAsStringLiteral(PANE_MODES).withDefault("log").withOptions({ history: "replace" }),
  );
}

/**
 * The agent canvas, open over the screen.
 *
 * A dialog rather than a route, which is the difference between looking at the
 * machinery and going somewhere else to look at it: the panels behind it keep
 * their widths, their selection and their scroll. In the URL so it is linkable,
 * which is what the second workspace was actually good for.
 */
export function useAgentSheet() {
  return useQueryState("graph", parseAsBoolean.withDefault(false).withOptions({ history: "replace" }));
}
