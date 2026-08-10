"use client";

import { parseAsBoolean, parseAsString, useQueryState } from "nuqs";

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
