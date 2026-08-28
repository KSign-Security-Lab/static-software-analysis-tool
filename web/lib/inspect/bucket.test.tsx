import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { clear, reconcile, resetAll, setMany, toggle, useBucket } from "./bucket";

function Ticks({ runId }: { runId: string | null }) {
  const ticked = useBucket(runId);
  return <output>{ticked.length === 0 ? "none" : [...ticked].sort().join(",")}</output>;
}

afterEach(cleanup);

beforeEach(() => {
  resetAll();
  window.sessionStorage.clear();
});

describe("the ticked set", () => {
  it("starts empty and toggles both ways", () => {
    render(<Ticks runId="r1" />);
    expect(screen.getByRole("status").textContent).toBe("none");

    act(() => toggle("r1", "f1"));
    expect(screen.getByRole("status").textContent).toBe("f1");

    act(() => toggle("r1", "f2"));
    expect(screen.getByRole("status").textContent).toBe("f1,f2");

    act(() => toggle("r1", "f1"));
    expect(screen.getByRole("status").textContent).toBe("f2");
  });

  it("ticks and clears a whole filtered view at once", () => {
    render(<Ticks runId="r1" />);
    act(() => setMany("r1", ["a", "b", "c"], true));
    expect(screen.getByRole("status").textContent).toBe("a,b,c");

    act(() => setMany("r1", ["a", "c"], false));
    expect(screen.getByRole("status").textContent).toBe("b");
  });

  it("empties on clear", () => {
    render(<Ticks runId="r1" />);
    act(() => setMany("r1", ["a", "b"], true));
    act(() => clear("r1"));
    expect(screen.getByRole("status").textContent).toBe("none");
  });

  it("keeps runs apart", () => {
    // A finding id is content-derived, so the same id in another run is the same
    // claim about different code. Carrying ticks across would build a patch
    // nobody asked for.
    render(<Ticks runId="r1" />);
    act(() => toggle("r1", "shared"));
    act(() => toggle("r2", "shared"));
    act(() => toggle("r2", "other"));
    expect(screen.getByRole("status").textContent).toBe("shared");
  });

  it("has nothing ticked when there is no run", () => {
    render(<Ticks runId={null} />);
    act(() => toggle("r1", "f1"));
    expect(screen.getByRole("status").textContent).toBe("none");
  });
});

describe("surviving a reload", () => {
  it("writes the ticks to session storage", () => {
    act(() => setMany("r1", ["f1", "f2"], true));
    expect(JSON.parse(window.sessionStorage.getItem("ssat.bucket.r1") ?? "[]").sort()).toEqual(["f1", "f2"]);
  });

  it("reads them back when the module has forgotten", () => {
    window.sessionStorage.setItem("ssat.bucket.r1", JSON.stringify(["f1", "f2"]));
    render(<Ticks runId="r1" />);
    // Triaging a real scan is minutes of decisions held in nothing but ticks.
    expect(screen.getByRole("status").textContent).toBe("f1,f2");
  });

  it("removes the key rather than storing an empty list", () => {
    act(() => toggle("r1", "f1"));
    act(() => clear("r1"));
    expect(window.sessionStorage.getItem("ssat.bucket.r1")).toBeNull();
  });

  it("ignores whatever else may be in storage under that key", () => {
    window.sessionStorage.setItem("ssat.bucket.r1", "not json");
    render(<Ticks runId="r1" />);
    expect(screen.getByRole("status").textContent).toBe("none");
  });

  it("ignores entries of the wrong shape", () => {
    window.sessionStorage.setItem("ssat.bucket.r1", JSON.stringify(["f1", 7, null, "f2"]));
    render(<Ticks runId="r1" />);
    expect(screen.getByRole("status").textContent).toBe("f1,f2");
  });
});

describe("reconcile", () => {
  it("drops ticks the report no longer has", () => {
    // The ordinary way this happens is a re-scan: ids are content-derived, so a
    // finding that was fixed comes back under a different id -- and a stale tick
    // would be counted in the tray and then refused by the server.
    render(<Ticks runId="r1" />);
    act(() => setMany("r1", ["stays", "gone"], true));
    act(() => reconcile("r1", ["stays", "new"]));
    expect(screen.getByRole("status").textContent).toBe("stays");
  });

  it("does nothing when every tick is still live", () => {
    render(<Ticks runId="r1" />);
    act(() => setMany("r1", ["a", "b"], true));
    act(() => reconcile("r1", new Set(["a", "b", "c"])));
    expect(screen.getByRole("status").textContent).toBe("a,b");
  });

  it("persists the reduced set", () => {
    act(() => setMany("r1", ["stays", "gone"], true));
    act(() => reconcile("r1", ["stays"]));
    expect(JSON.parse(window.sessionStorage.getItem("ssat.bucket.r1") ?? "[]")).toEqual(["stays"]);
  });
});
