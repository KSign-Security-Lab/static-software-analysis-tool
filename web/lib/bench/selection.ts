"use client";

import { useSyncExternalStore } from "react";

/**
 * Which instances are ticked, shared between the list and the run panel.
 *
 * The list lives in the `@side` slot and the run button in the main one, so
 * they are not in the same tree. Same shape as `lib/run/whoami`: a module store
 * plus `useSyncExternalStore`, which is the smallest thing that lets two slots
 * agree.
 *
 * Not in the URL. A hundred instance ids is not a link anyone can send, and the
 * one selection worth sharing -- a single instance -- is already `?instance=`.
 *
 * Keyed by dataset, because the two SEC-bench splits are separate runs: a tick
 * carried from one to the other would start a sweep over ids the split does not
 * contain.
 */

const chosen = new Map<string, Set<string>>();
const listeners = new Set<() => void>();

function notify(): void {
  for (const listener of listeners) listener();
}

function bucket(dataset: string): Set<string> {
  const found = chosen.get(dataset);
  if (found) return found;
  const made = new Set<string>();
  chosen.set(dataset, made);
  return made;
}

export function toggle(dataset: string, id: string): void {
  const set = bucket(dataset);
  if (set.has(id)) set.delete(id);
  else set.add(id);
  notify();
}

/** Tick or clear a whole group at once -- 196 rows is not a thing to click. */
export function setMany(dataset: string, ids: string[], on: boolean): void {
  const set = bucket(dataset);
  for (const id of ids) {
    if (on) set.add(id);
    else set.delete(id);
  }
  notify();
}

export function clear(dataset: string): void {
  if (bucket(dataset).size === 0) return;
  chosen.set(dataset, new Set());
  notify();
}

// Snapshots must be referentially stable or `useSyncExternalStore` loops: it
// compares the value it just read against the previous one, and a fresh array
// every call never matches.
const cache = new Map<string, string[]>();
const EMPTY: string[] = [];

function snapshot(dataset: string): string[] {
  const set = chosen.get(dataset);
  if (!set || set.size === 0) return EMPTY;
  const found = cache.get(dataset);
  if (found && found.length === set.size && found.every((id) => set.has(id))) return found;
  const made = [...set];
  cache.set(dataset, made);
  return made;
}

export function useSelection(dataset: string): string[] {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => snapshot(dataset),
    () => EMPTY,
  );
}
