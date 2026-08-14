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
 * Whether the transcript is narrowed to the open finding's own chain.
 *
 * On by default: opening a claim and being shown all forty conversations, one of
 * which is the reason for it, is not an answer.
 *
 * In the URL, and that is a fix rather than a preference. It was `useState` in
 * `InspectorPane` plus a render-phase reset whenever `?finding=` changed, so
 * "show me the whole run" silently undid itself every time the reader opened a
 * different problem -- and nothing outside that one pane could see the narrowing
 * or offer a way out of it. The context strip needs to name it, which means it
 * has to be somewhere the strip can read.
 *
 * It also no longer resets per finding. Turning the narrowing off is a way of
 * reading, not a fact about one claim.
 */
export function useClaimScope() {
  return useQueryState("claim", parseAsBoolean.withDefault(true).withOptions({ history: "replace" }));
}
