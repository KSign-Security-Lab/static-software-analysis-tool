import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuqsTestingAdapter, type OnUrlUpdateFunction } from "nuqs/adapters/testing";
import { afterEach, describe, expect, it, vi } from "vitest";

import { idOf, useSelection, useSort, type Selection } from "./selection";

/**
 * One selection at a time, and the one exception to it.
 *
 * Several params could be set at once -- `finding`, `span`, and once `node` and
 * `cp` too -- each written by whichever pane owned it. Nothing on screen could
 * then state what the detail column was showing, and clearing one left the
 * others set. "Exactly one" has to be a property of the hook rather than a
 * convention its callers follow, which is what these pin.
 *
 * The exception is a call, which is a *step of* the open finding rather than an
 * alternative to it, so selecting one deliberately keeps `?finding=`.
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
  ])("reads a %s", (kind, search, id) => {
    show(search);
    expect(screen.getByTestId("kind").textContent).toBe(kind);
    expect(screen.getByTestId("id").textContent).toBe(id);
  });

  it("prefers the call when both are set, because it is the narrower reading", () => {
    // The ordinary state while reading 판단 과정: the finding stays open and one
    // of its steps is being read.
    show({ finding: "agent:f1", span: "span-gather" });
    expect(screen.getByTestId("kind").textContent).toBe("call");
  });
});

describe("selecting", () => {
  it("keeps the finding open when a call inside it is selected", async () => {
    // A call is only ever interesting as a step in an argument, so opening one
    // must not cost the reader the claim it belongs to.
    const onUrlUpdate = vi.fn();
    show({ finding: "agent:f1" }, { kind: "call", id: "span-gather" }, onUrlUpdate);

    await userEvent.click(screen.getByText("select"));

    expect(params(onUrlUpdate).get("span")).toBe("span-gather");
    expect(params(onUrlUpdate).get("finding")).toBe("agent:f1");
  });

  it("drops an open call when a different finding is selected", async () => {
    // The step belonged to the finding being left behind.
    const onUrlUpdate = vi.fn();
    show({ finding: "agent:f1", span: "span-gather" }, { kind: "finding", id: "agent:f2" }, onUrlUpdate);

    await userEvent.click(screen.getByText("select"));

    expect(params(onUrlUpdate).get("finding")).toBe("agent:f2");
    expect(params(onUrlUpdate).get("span")).toBeNull();
  });

  it("leaves everything else in the URL alone", async () => {
    // The run and the sort are not the selection.
    const onUrlUpdate = vi.fn();
    show({ run: "abc", sort: "file" }, { kind: "finding", id: "agent:f1" }, onUrlUpdate);

    await userEvent.click(screen.getByText("select"));

    expect(params(onUrlUpdate).get("run")).toBe("abc");
    expect(params(onUrlUpdate).get("sort")).toBe("file");
  });

  it("clears both on clear", async () => {
    const onUrlUpdate = vi.fn();
    show({ finding: "agent:f1", span: "span-gather" }, null, onUrlUpdate);

    await userEvent.click(screen.getByText("clear"));

    for (const key of ["finding", "span"]) {
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

describe("the row order", () => {
  function SortHarness() {
    const [sort, setSort] = useSort();
    return (
      <div>
        <span data-testid="sort">{sort}</span>
        <button type="button" onClick={() => void setSort("file")}>
          by file
        </button>
      </div>
    );
  }

  const showSort = (searchParams: Record<string, string>, onUrlUpdate?: OnUrlUpdateFunction) =>
    render(
      <NuqsTestingAdapter searchParams={searchParams} onUrlUpdate={onUrlUpdate}>
        <SortHarness />
      </NuqsTestingAdapter>,
    );

  it("opens on the worst thing found", () => {
    showSort({});
    expect(screen.getByTestId("sort").textContent).toBe("severity");
  });

  it("carries a real order in the URL", async () => {
    const onUrlUpdate = vi.fn();
    showSort({}, onUrlUpdate);
    await userEvent.click(screen.getByText("by file"));
    expect(params(onUrlUpdate).get("sort")).toBe("file");
  });

  it("ignores an order it does not have", () => {
    showSort({ sort: "nonsense" });
    expect(screen.getByTestId("sort").textContent).toBe("severity");
  });
});
