"use client";

import { parseAsString, parseAsStringLiteral, useQueryState } from "nuqs";

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

export const CENTRE_VIEWS = ["code", "graph"] as const;
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

export const INSPECTOR_VIEWS = ["finding", "span"] as const;
export type InspectorView = (typeof INSPECTOR_VIEWS)[number];

/**
 * Which of the two inspectors the right pane is showing.
 *
 * Set by whichever list was last clicked -- a finding in 문제, a call in 호출
 * 기록 -- so the pane answers about the thing you just picked. Both remain one
 * click away, because hiding the other would make the tab you are not on look
 * like it had no content.
 */
export function useInspectorView() {
  return useQueryState(
    "insp",
    parseAsStringLiteral(INSPECTOR_VIEWS).withDefault("finding").withOptions({ history: "replace" }),
  );
}
