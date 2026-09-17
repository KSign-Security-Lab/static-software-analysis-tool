"use client";

import { useSyncExternalStore } from "react";

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
