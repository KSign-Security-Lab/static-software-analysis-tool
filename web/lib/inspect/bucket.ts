"use client";

import { useSyncExternalStore } from "react";

/**
 * The findings a reader has picked out to fix.
 *
 * Triaging a real scan means reading dozens of rows and deciding about each one,
 * which is minutes of work held in nothing but a set of ticks. So it survives a
 * reload: `sessionStorage`, keyed by run, the same reasoning as `lib/run/session`
 * -- it belongs to this tab and closing the tab lets go.
 *
 * Not in the URL. Forty finding ids is not a link anybody can send, and the one
 * selection worth sharing -- which finding is open -- is already `?finding=`.
 *
 * Keyed by run because a tick means nothing outside the report it came from: a
 * finding id is content-derived, so the same id in another run is the same claim
 * about different code, and carrying ticks across would build a patch nobody
 * asked for.
 *
 * A module store plus `useSyncExternalStore`, matching `lib/bench/selection` and
 * `lib/run/whoami`: the table, the detail panel and the tray are not in one
 * subtree, and this is the smallest thing that lets all three agree.
 */

const KEY_PREFIX = "ssat.bucket.";

const chosen = new Map<string, Set<string>>();
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

function keyFor(runId: string): string {
  return `${KEY_PREFIX}${runId}`;
}

function persist(runId: string, set: Set<string>): void {
  if (typeof window === "undefined") return;
  try {
    if (set.size === 0) window.sessionStorage.removeItem(keyFor(runId));
    else window.sessionStorage.setItem(keyFor(runId), JSON.stringify([...set]));
  } catch {
    /* storage can be denied outright; the ticks still work for this page load */
  }
}

function restore(runId: string): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = window.sessionStorage.getItem(keyFor(runId));
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    // Anything could be in storage -- an older shape, a truncated write.
    return Array.isArray(parsed) ? new Set(parsed.filter((id): id is string => typeof id === "string")) : new Set();
  } catch {
    return new Set();
  }
}

function bucket(runId: string): Set<string> {
  const found = chosen.get(runId);
  if (found) return found;
  const made = restore(runId);
  chosen.set(runId, made);
  return made;
}

export function toggle(runId: string, id: string): void {
  const set = bucket(runId);
  if (set.has(id)) set.delete(id);
  else set.add(id);
  persist(runId, set);
  notify();
}

/** Tick or clear a whole filtered view at once. Two hundred rows is not clicking. */
export function setMany(runId: string, ids: string[], on: boolean): void {
  const set = bucket(runId);
  for (const id of ids) {
    if (on) set.add(id);
    else set.delete(id);
  }
  persist(runId, set);
  notify();
}

export function clear(runId: string): void {
  if (bucket(runId).size === 0) return;
  chosen.set(runId, new Set());
  persist(runId, new Set());
  notify();
}

/**
 * Drop ticks for findings the report no longer has.
 *
 * A re-scan is the ordinary way this happens: finding ids are content-derived,
 * so anything that was fixed or has moved comes back under a different id, and
 * a stale tick would be counted in the tray and then refused by the server as
 * an unknown finding. Reconciling here means the count on screen is always a
 * count of things that can actually be patched.
 */
export function reconcile(runId: string, known: Iterable<string>): void {
  const set = bucket(runId);
  if (set.size === 0) return;
  const live = known instanceof Set ? known : new Set(known);
  let dropped = false;
  for (const id of [...set]) {
    if (!live.has(id)) {
      set.delete(id);
      dropped = true;
    }
  }
  if (!dropped) return;
  persist(runId, set);
  notify();
}

// Snapshots must be referentially stable or `useSyncExternalStore` loops: it
// compares what it just read against the previous value, and a fresh array
// every call never matches.
const cache = new Map<string, string[]>();
const EMPTY: string[] = [];

function snapshot(runId: string | null): string[] {
  if (!runId) return EMPTY;
  const set = bucket(runId);
  if (set.size === 0) return EMPTY;
  const found = cache.get(runId);
  if (found && found.length === set.size && found.every((id) => set.has(id))) return found;
  const made = [...set];
  cache.set(runId, made);
  return made;
}

/** The ticked ids for this run, stable between renders. */
export function useBucket(runId: string | null): string[] {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => snapshot(runId),
    // The server has no session storage, so the first paint has nothing ticked.
    () => EMPTY,
  );
}

/** For tests: forget everything, including what was written to storage. */
export function resetAll(): void {
  for (const runId of chosen.keys()) persist(runId, new Set());
  chosen.clear();
  cache.clear();
  notify();
}
