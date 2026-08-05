"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * How the trace view is arranged, remembered between visits.
 *
 * In `localStorage`, not `sessionStorage`, and deliberately unlike the run id
 * next door in `session.ts`: which run you are looking at belongs to this tab,
 * but how big you like the graph is a preference, and having to drag it back
 * every time you open the page would be its own small insult.
 */

const KEY = "ssat-studio-panes";

export interface Panes {
  /** The structure strip's share of the centre column, 0-1. */
  graph: number;
  graphOpen: boolean;
  stepsOpen: boolean;
  detailOpen: boolean;
}

/** The agent's graph gets the largest single share; it is what people look at. */
export const DEFAULT_PANES: Panes = { graph: 0.42, graphOpen: true, stepsOpen: true, detailOpen: true };

/** Small enough to still be a graph, large enough to leave the trace readable. */
export const MIN_GRAPH = 0.2;
export const MAX_GRAPH = 0.7;

export function clampGraph(share: number): number {
  if (!Number.isFinite(share)) return DEFAULT_PANES.graph;
  return Math.min(MAX_GRAPH, Math.max(MIN_GRAPH, share));
}

export function readPanes(): Panes {
  if (typeof window === "undefined") return DEFAULT_PANES;
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return DEFAULT_PANES;
    const stored = JSON.parse(raw) as Partial<Panes>;
    return {
      graph: clampGraph(typeof stored.graph === "number" ? stored.graph : DEFAULT_PANES.graph),
      graphOpen: stored.graphOpen !== false,
      stepsOpen: stored.stepsOpen !== false,
      detailOpen: stored.detailOpen !== false,
    };
  } catch {
    // Storage denied, or something else wrote nonsense under this key. Neither
    // is a reason to fail to lay out a page.
    return DEFAULT_PANES;
  }
}

export function writePanes(panes: Panes): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(panes));
  } catch {
    /* private mode, or a full quota. The layout still works for this visit. */
  }
}

/**
 * The layout, as state. Read on mount rather than during render: there is no
 * `localStorage` on the server, and reading it in render would make the first
 * paint disagree with the markup React sent.
 */
export function usePanes(): [Panes, (update: Partial<Panes>) => void] {
  const [panes, setPanes] = useState<Panes>(DEFAULT_PANES);

  useEffect(() => setPanes(readPanes()), []);

  const update = useCallback((change: Partial<Panes>) => {
    setPanes((current) => {
      const next = { ...current, ...change };
      if (change.graph !== undefined) next.graph = clampGraph(change.graph);
      writePanes(next);
      return next;
    });
  }, []);

  return [panes, update];
}
