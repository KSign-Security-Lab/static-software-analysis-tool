"use client";

import { useQueryState } from "nuqs";
import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { perspectiveFor } from "@/lib/workbench/perspectives";
import { clearRestored, markRestored, readSessionRun, wasRestored, writeSessionRun } from "./session";

/**
 * Which run the workbench is looking at.
 *
 * The URL is authoritative and the tab's session is the fallback, in that
 * order. Two properties fall out of that and both are the point:
 *
 *  - `?run=` in a link wins, so a trace can be sent to a colleague without
 *    also handing them a list of everyone else's runs.
 *  - opening the trace with only a remembered run *writes it back into the
 *    URL*, so the address bar is immediately shareable. The old version left
 *    it bare, and ⌘L produced a link that showed the recipient nothing.
 *
 * `push` history, unlike the other params: changing which run you are looking
 * at is a navigation, and back should undo it.
 *
 * Setting it to `null` forgets the run in both places. It has to: the fallback
 * below cannot tell "the URL never had one" from "the run was just deleted", so
 * clearing only the URL let the effect read the tab's memory and put the dead id
 * straight back -- and every query then asked the server for a run that was no
 * longer there.
 */

/**
 * Whether this surface has any business with a run.
 *
 * `carries` in perspectives.ts already declares it, and the restore effect was
 * ignoring it -- so leaving 검사 for F2-A produced `/f2a?run=…`: `hrefFor`
 * correctly dropped the id on the way out and this put it straight back. Two
 * mechanisms with opposite opinions about the same param, and the one nobody
 * declared won.
 */
function wantsRun(pathname: string): boolean {
  return perspectiveFor(pathname)?.carries.includes("run") ?? false;
}

export interface RunIdState {
  runId: string | null;
  setRunId: (id: string | null) => void;
  /**
   * True when the id came from the tab's memory rather than from the link.
   *
   * Nothing could tell the two apart before, so a bare `/agent` silently opened
   * whatever you last scanned and looked identical to having asked for it. The
   * convenience is worth keeping; doing it without saying so is not. The context
   * strip reads this to say 이어서 보는 중.
   */
  restored: boolean;
}

export function useRunState(): RunIdState {
  const pathname = usePathname();
  const [runId, setQueryRunId] = useQueryState("run", { history: "push" });

  const wanted = wantsRun(pathname);

  useEffect(() => {
    if (runId) {
      // Only remember it where it means something. Writing from a surface that
      // does not carry `run` would let F2-A decide what 검사 opens next.
      if (wanted) writeSessionRun(runId);
      return;
    }
    if (!wanted) return;
    // No effect-then-setState here: this writes to the URL, which is external
    // state, and only when the URL is the thing that is missing information.
    const remembered = readSessionRun();
    if (remembered) {
      // Recorded outside React -- see session.ts for why it lives there.
      markRestored();
      void setQueryRunId(remembered, { history: "replace" });
    }
  }, [runId, wanted, setQueryRunId]);

  return {
    runId,
    restored: wasRestored() && Boolean(runId),
    setRunId: (id) => {
      // Asked for by hand, so it is no longer something we put there.
      clearRestored();
      // Before the URL write, so the effect it triggers reads an empty session
      // rather than the one being cleared.
      if (id === null) writeSessionRun(null);
      void setQueryRunId(id);
    },
  };
}

/** The tuple form, for the many callers that only want the id. */
export function useRunId(): [string | null, (id: string | null) => void] {
  const { runId, setRunId } = useRunState();
  return [runId, setRunId];
}
