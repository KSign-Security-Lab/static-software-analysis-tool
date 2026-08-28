/**
 * A name somebody typed, so the run list is theirs rather than everyone's.
 *
 * **This is not a login and must never be treated as one.** Nothing is
 * challenged, nothing is verified, and typing someone else's name is a text
 * field away. A run is still readable by id whoever asks. It exists for one
 * reason: the server is shared, and a list of every scan on the box is mostly
 * other people's and useless -- nobody recognises a stranger's run.
 *
 * `localStorage`, unlike the current run in {@link "./session"}: the run
 * belongs to the tab and closing it lets go, but who you are should survive a
 * reload. Asked once, on first visit.
 */

export const WHOAMI_KEY = "ssat.owner";

/** The header the API reads. Mirrors `OWNER_HEADER` in `api/agent/deps.py`. */
export const OWNER_HEADER = "x-ssat-owner";

/** Matches the column: trimmed, and bounded because it is echoed into a list. */
export const MAX_NAME = 128;

export function normalise(raw: string): string {
  return raw.trim().slice(0, MAX_NAME);
}

export function readOwner(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(WHOAMI_KEY) || null;
  } catch {
    // Storage can be denied outright. Then every run is anonymous, which is
    // what this was before it existed -- usable, just less tidy.
    return null;
  }
}

export function writeOwner(name: string | null): void {
  if (typeof window === "undefined") return;
  try {
    const value = name ? normalise(name) : "";
    if (value) window.localStorage.setItem(WHOAMI_KEY, value);
    else window.localStorage.removeItem(WHOAMI_KEY);
  } catch {
    /* nothing to do: the page works without a remembered name */
  }
  notify();
}

type Listener = () => void;
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener();
}

/**
 * For `useSyncExternalStore`. The dialog writes and the header reads, and they
 * are not in the same tree.
 */
export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Headers to merge into a request, or nothing when no name has been given. */
export function ownerHeaders(): Record<string, string> {
  const name = readOwner();
  return name ? { [OWNER_HEADER]: name } : {};
}
