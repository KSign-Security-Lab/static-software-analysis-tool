"use client";

import { useQueryState } from "nuqs";
import { useEffect } from "react";

import { readSessionRun, writeSessionRun } from "./session";

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
export function useRunId(): [string | null, (id: string | null) => void] {
  const [runId, setRunId] = useQueryState("run", { history: "push" });

  useEffect(() => {
    if (runId) {
      writeSessionRun(runId);
      return;
    }
    // No effect-then-setState here: this writes to the URL, which is external
    // state, and only when the URL is the thing that is missing information.
    const remembered = readSessionRun();
    if (remembered) void setRunId(remembered, { history: "replace" });
  }, [runId, setRunId]);

  return [
    runId,
    (id) => {
      // Before the URL write, so the effect it triggers reads an empty session
      // rather than the one being cleared.
      if (id === null) writeSessionRun(null);
      void setRunId(id);
    },
  ];
}
