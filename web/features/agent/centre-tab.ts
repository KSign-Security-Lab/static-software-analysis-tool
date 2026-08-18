"use client";

import { parseAsStringLiteral, useQueryState } from "nuqs";

/**
 * Which artifact the centre is showing.
 *
 * Its own module rather than a field on `useSelection`, because it is not a
 * selection: the selection is *what* is being read, this is *which face* of it.
 * They compose -- a finding stays selected while you look at its patch, which is
 * the whole reason the patch moved out of the right column.
 *
 * `code` is the default and drops out of the address bar, so a bare link opens
 * on the file rather than on the machinery.
 */
export const CENTRE_TABS = ["code", "fix", "process", "graph"] as const;
export type CentreTab = (typeof CENTRE_TABS)[number];

export function useCentreTab() {
  return useQueryState(
    "view",
    parseAsStringLiteral(CENTRE_TABS).withDefault("code").withOptions({ history: "replace" }),
  );
}
