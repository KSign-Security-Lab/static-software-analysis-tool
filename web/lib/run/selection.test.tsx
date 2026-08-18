import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuqsTestingAdapter, type OnUrlUpdateFunction } from "nuqs/adapters/testing";
import { afterEach, describe, expect, it, vi } from "vitest";

import { idOf, useFilter, useSelection, type Selection } from "./selection";

/**
 * One selection at a time.
 *
 * Four params could be set at once -- `finding`, `span`, `node`, `cp` -- each
 * written by whichever pane owned it. Nothing on screen could then state what the
 * right-hand pane was showing, and clearing one left the others set. "Exactly
 * one" has to be a property of the hook, not a convention five callers follow,
 * which is what these pin.
 */

afterEach(cleanup);

function Harness({ next }: { next: Selection }) {
  const { selection, select, clear } = useSelection();
  return (
    <div>
      <span data-testid="kind">{selection?.kind ?? "none"}</span>
      <span data-testid="id">{selection?.id ?? ""}</span>
      <button type="button" onClick={() => select(next)}>
        select
      </button>
      <button type="button" onClick={clear}>
        clear
      </button>
    </div>
  );
}

function show(searchParams: Record<string, string>, next: Selection = null, onUrlUpdate?: OnUrlUpdateFunction) {
  return render(
    <NuqsTestingAdapter searchParams={searchParams} onUrlUpdate={onUrlUpdate}>
      <Harness next={next} />
    </NuqsTestingAdapter>,
  );
}

const params = (onUrlUpdate: ReturnType<typeof vi.fn>) => onUrlUpdate.mock.calls.at(-1)![0].searchParams;

describe("reading the selection", () => {
  it("is nothing when nothing is selected", () => {
    show({});
    expect(screen.getByTestId("kind").textContent).toBe("none");
  });

  it.each([
    ["finding", { finding: "agent:f1" }, "agent:f1"],
    ["call", { span: "span-gather" }, "span-gather"],
    ["node", { node: "verify" }, "verify"],
  ])("reads a %s", (kind, search, id) => {
    show(search);
    expect(screen.getByTestId("kind").textContent).toBe(kind);
    expect(screen.getByTestId("id").textContent).toBe(id);
  });

  it("prefers the finding when a hand-written URL sets two", () => {
    // Only reachable by typing a URL: `select` cannot produce this state. The
    // point is that it resolves to one thing rather than rendering two.
    show({ finding: "agent:f1", node: "verify" });
    expect(screen.getByTestId("kind").textContent).toBe("finding");
  });
});

describe("selecting", () => {
  it("clears every other kind, not just the one the caller knew about", async () => {
    const onUrlUpdate = vi.fn();
    show({ finding: "agent:f1", node: "verify", cp: "cp-3" }, { kind: "call", id: "span-gather" }, onUrlUpdate);

    await userEvent.click(screen.getByText("select"));

    expect(params(onUrlUpdate).get("span")).toBe("span-gather");
    expect(params(onUrlUpdate).get("finding")).toBeNull();
    expect(params(onUrlUpdate).get("node")).toBeNull();
      });

  it("leaves everything else in the URL alone", async () => {
    // The run, the open file and the line are not the selection.
    const onUrlUpdate = vi.fn();
    show({ run: "abc", file: "main.c", line: "6" }, { kind: "node", id: "verify" }, onUrlUpdate);

    await userEvent.click(screen.getByText("select"));

    expect(params(onUrlUpdate).get("run")).toBe("abc");
    expect(params(onUrlUpdate).get("file")).toBe("main.c");
    expect(params(onUrlUpdate).get("line")).toBe("6");
  });

  it("clears all three on clear", async () => {
    const onUrlUpdate = vi.fn();
    show({ finding: "agent:f1" }, null, onUrlUpdate);

    await userEvent.click(screen.getByText("clear"));

    for (const key of ["finding", "span", "node"]) {
      expect(params(onUrlUpdate).get(key)).toBeNull();
    }
  });
});

describe("idOf", () => {
  it("answers only for the kind asked about", () => {
    const selection: Selection = { kind: "call", id: "span-gather" };
    expect(idOf(selection, "call")).toBe("span-gather");
    expect(idOf(selection, "finding")).toBeNull();
    expect(idOf(null, "call")).toBeNull();
  });
});

describe("the list filter", () => {
  function FilterHarness() {
    const [filter, setFilter] = useFilter();
    return (
      <div>
        <span data-testid="filter">{filter}</span>
        <button type="button" onClick={() => void setFilter("all")}>
          all
        </button>
      </div>
    );
  }

  const showFilter = (searchParams: Record<string, string>, onUrlUpdate?: OnUrlUpdateFunction) =>
    render(
      <NuqsTestingAdapter searchParams={searchParams} onUrlUpdate={onUrlUpdate}>
        <FilterHarness />
      </NuqsTestingAdapter>,
    );

  it("opens on the problems, not on the machinery", () => {
    showFilter({});
    expect(screen.getByTestId("filter").textContent).toBe("problems");
  });

  it("drops out of the URL at its default", async () => {
    const onUrlUpdate = vi.fn();
    showFilter({ show: "tools" }, onUrlUpdate);
    await userEvent.click(screen.getByText("all"));
    expect(params(onUrlUpdate).get("show")).toBe("all");
  });

  it("ignores a filter it does not have", () => {
    showFilter({ show: "nonsense" });
    expect(screen.getByTestId("filter").textContent).toBe("problems");
  });
});
