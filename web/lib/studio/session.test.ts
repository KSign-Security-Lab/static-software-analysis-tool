import { beforeEach, describe, expect, it, vi } from "vitest";

import { currentRun, setCurrentRun } from "./session";

/** A tab's sessionStorage, and a URL we can move around. */
function browser(search = "") {
  const store = new Map<string, string>();
  vi.stubGlobal("window", {
    location: { search },
    sessionStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
      removeItem: (k: string) => void store.delete(k),
    },
  });
  return store;
}

describe("the session's run", () => {
  beforeEach(() => vi.unstubAllGlobals());

  it("is nothing until something puts one there", () => {
    browser();
    expect(currentRun()).toBeNull();
  });

  it("survives moving between the two tabs of the section", () => {
    browser();
    setCurrentRun("abc123");
    expect(currentRun()).toBe("abc123");
  });

  it("is let go of when cleared", () => {
    browser();
    setCurrentRun("abc123");
    setCurrentRun(null);
    expect(currentRun()).toBeNull();
  });

  it("adopts a run linked to in the URL", () => {
    // What makes a trace shareable: opening the link joins that run rather
    // than showing whatever this tab was last looking at.
    const store = browser("?run=fromlink");
    setCurrentRun("older");

    expect(currentRun()).toBe("fromlink");
    expect(store.get("ssat-studio-run")).toBe("fromlink");
  });

  it("works on a server render, where there is no window at all", () => {
    vi.stubGlobal("window", undefined);
    expect(currentRun()).toBeNull();
    expect(() => setCurrentRun("x")).not.toThrow();
  });

  it("survives storage being denied", () => {
    // Private browsing and some policies throw on access rather than returning
    // null. A session with no memory is still a usable page.
    vi.stubGlobal("window", {
      location: { search: "" },
      sessionStorage: {
        getItem: () => {
          throw new Error("denied");
        },
        setItem: () => {
          throw new Error("denied");
        },
        removeItem: () => {
          throw new Error("denied");
        },
      },
    });

    expect(currentRun()).toBeNull();
    expect(() => setCurrentRun("x")).not.toThrow();
  });
});
