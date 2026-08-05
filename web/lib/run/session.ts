/**
 * The run this browser tab is working on.
 *
 * The runs directory is shared by everyone using the server, so a list of every
 * run on the box is both other people's business and useless -- nobody
 * recognises a stranger's run. What you want to trace is the code you just put
 * in.
 *
 * `sessionStorage`, not `localStorage`: it belongs to this tab, and closing it
 * lets go.
 */

export const RUN_KEY = "ssat.run";

export function readSessionRun(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage.getItem(RUN_KEY);
  } catch {
    // Storage can be denied outright; a tab with no memory is still usable.
    return null;
  }
}

export function writeSessionRun(runId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (runId) window.sessionStorage.setItem(RUN_KEY, runId);
    else window.sessionStorage.removeItem(RUN_KEY);
  } catch {
    /* nothing to do: the page works without a remembered run */
  }
}
