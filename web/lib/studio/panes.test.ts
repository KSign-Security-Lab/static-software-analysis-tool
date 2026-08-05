import { beforeEach, describe, expect, it, vi } from "vitest";

import { DEFAULT_PANES, MAX_GRAPH, MIN_GRAPH, clampGraph, readPanes, writePanes } from "./panes";

/** A browser with a localStorage, the way `session.test.ts` fakes one. */
function browser(): Map<string, string> {
  const store = new Map<string, string>();
  vi.stubGlobal("window", {
    localStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    },
  });
  return store;
}

/** Storage that refuses, as it does in private mode or over quota. */
function deniedStorage(): void {
  const refuse = () => {
    throw new Error("denied");
  };
  vi.stubGlobal("window", { localStorage: { getItem: refuse, setItem: refuse, removeItem: refuse } });
}

describe("panes", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("opens everything by default", () => {
    browser();
    // The graph, the steps and the selected call are all things people came
    // here to read. Hiding one behind a click they have to discover is not a
    // saving.
    expect(DEFAULT_PANES.graphOpen).toBe(true);
    expect(DEFAULT_PANES.stepsOpen).toBe(true);
    expect(DEFAULT_PANES.detailOpen).toBe(true);
    expect(readPanes()).toEqual(DEFAULT_PANES);
  });

  it("gives the graph the largest single share", () => {
    expect(DEFAULT_PANES.graph).toBeGreaterThan(0.35);
    expect(DEFAULT_PANES.graph).toBeLessThanOrEqual(MAX_GRAPH);
  });

  it("keeps the split inside bounds however it is asked", () => {
    browser();
    // A drag that leaves the window, or a stored value from a build where the
    // bounds were different.
    expect(clampGraph(0)).toBe(MIN_GRAPH);
    expect(clampGraph(5)).toBe(MAX_GRAPH);
    expect(clampGraph(Number.NaN)).toBe(DEFAULT_PANES.graph);
    expect(clampGraph(0.5)).toBe(0.5);
  });

  it("remembers the layout across visits", () => {
    browser();
    // localStorage, unlike the run id next door: which run you are looking at
    // belongs to the tab, but how big you like the graph is a preference.
    writePanes({ graph: 0.55, graphOpen: false, stepsOpen: false, detailOpen: true });
    expect(readPanes()).toEqual({ graph: 0.55, graphOpen: false, stepsOpen: false, detailOpen: true });
  });

  it("falls back to the default rather than failing to lay out a page", () => {
    const store = browser();
    store.set("ssat-studio-panes", "{not json");
    expect(readPanes()).toEqual(DEFAULT_PANES);

    store.set("ssat-studio-panes", JSON.stringify({ graph: 99 }));
    expect(readPanes().graph).toBe(MAX_GRAPH);
  });

  it("survives storage being denied, and the server, where there is none", () => {
    deniedStorage();
    expect(readPanes()).toEqual(DEFAULT_PANES);
    expect(() => writePanes(DEFAULT_PANES)).not.toThrow();

    vi.unstubAllGlobals();
    expect(readPanes()).toEqual(DEFAULT_PANES);
    expect(() => writePanes(DEFAULT_PANES)).not.toThrow();
  });
});
