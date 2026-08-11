"use client";

import { parseAsInteger, parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";

/**
 * What the inspect surface is looking at, in the URL.
 *
 * `file` and `finding` are `replace` history: clicking through a findings list
 * should not fill the back stack with twenty entries. `run` is `push`, and
 * lives in lib/run/use-run-id.ts because the stream needs it too.
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

export const CENTRE_VIEWS = ["code", "graph", "map", "state"] as const;
export type CentreView = (typeof CENTRE_VIEWS)[number];

/**
 * Which view the centre pane is showing: the code, or the run that read it.
 *
 * `centre`, not `view`: 추출 and F2-A already own a `view` param with entirely
 * different values, and `hrefFor` copies a param by name when both
 * perspectives claim it -- so sharing the word would carry `view=code` into a
 * graph picker that has no such view.
 *
 * In the URL because it is what you are looking at, not how the window is
 * arranged, and a link to a run in progress should be able to say "open on the
 * graph". `replace`, so flipping tabs does not fill the back stack.
 */
export function useCentreView() {
  return useQueryState(
    "centre",
    parseAsStringLiteral(CENTRE_VIEWS).withDefault("code").withOptions({ history: "replace" }),
  );
}
