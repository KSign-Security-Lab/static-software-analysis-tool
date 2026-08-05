"use client";

/**
 * The run this browser session is working on.
 *
 * The runs directory is shared by everyone using the server, so a list of every
 * run on the box is both other people's business and useless: nobody recognises
 * a stranger's run. What you want to trace is the code you just put in.
 *
 * Kept in `sessionStorage` rather than `localStorage`, so it belongs to this tab
 * and closing it lets go. A `?run=` in the URL wins and is adopted, which is
 * what makes a trace linkable to a colleague without giving them the whole list.
 */

const KEY = "ssat-studio-run";

export function currentRun(): string | null {
  if (typeof window === "undefined") return null;

  const linked = new URLSearchParams(window.location.search).get("run");
  if (linked) {
    setCurrentRun(linked);
    return linked;
  }
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    // Storage can be denied outright; a session with no memory is still usable.
    return null;
  }
}

export function setCurrentRun(runId: string | null): void {
  if (typeof window === "undefined") return;
  try {
    if (runId) window.sessionStorage.setItem(KEY, runId);
    else window.sessionStorage.removeItem(KEY);
  } catch {
    /* nothing to do: the page works without a remembered run */
  }
}
