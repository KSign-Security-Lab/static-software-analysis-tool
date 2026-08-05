"use client";

import { parseAsString, useQueryState } from "nuqs";

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
