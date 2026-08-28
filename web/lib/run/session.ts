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

/**
 * Whether the run on screen was reopened from this memory rather than asked for.
 *
 * A module variable, and deliberately not React state. It is one fact about this
 * page load -- "the id in the URL is ours, not theirs" -- and every way of
 * holding it inside a hook was worse: `useState` means a second render pass to
 * record what the accompanying URL write already re-renders for, and a `useRef`
 * read during render is what the hooks lint quite reasonably forbids.
 *
 * It exists because nothing could tell the two apart, so a bare `/agent`
 * silently reopened whatever you last scanned and looked exactly like having
 * asked for it. The convenience is worth keeping; doing it without saying so is
 * not, and the context strip says so by reading this.
 */
let restoredHere = false;

export function markRestored(): void {
  restoredHere = true;
}

/** Forget it: the reader has since chosen a run themselves. */
export function clearRestored(): void {
  restoredHere = false;
}

export function wasRestored(): boolean {
  return restoredHere;
}
