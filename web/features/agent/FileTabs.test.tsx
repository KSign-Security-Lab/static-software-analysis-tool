import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { FileCount } from "@/lib/model/finding";
import FileTabs from "./FileTabs";

/**
 * The files a reader has open, and which one they are looking at.
 *
 * Worth covering because of what it is for. `?file=` is one parameter, so before
 * this existed every step of an evidence trail *replaced* the open file: a claim
 * whose 유입 is in `main.c` and whose 위험 지점 is in `util.c` walked the reader
 * across two files and left no way back to the first. The assertions below are
 * about that -- the strip remembers, and closing does not strand you.
 */

afterEach(cleanup);

const counts = new Map<string, FileCount>([
  ["src/main.c", { total: 2, worst: "critical" }],
  ["src/util.c", { total: 0, worst: null }],
]);

function draw(over: Partial<React.ComponentProps<typeof FileTabs>> = {}) {
  const onPick = vi.fn();
  const onClose = vi.fn();
  const view = render(
    <FileTabs
      open={["src/main.c", "src/util.c"]}
      active="src/main.c"
      dirty={[]}
      counts={counts}
      onPick={onPick}
      onClose={onClose}
      {...over}
    />,
  );
  return { ...view, onPick, onClose };
}

describe("the strip", () => {
  it("is not there when nothing is open", () => {
    const { container } = draw({ open: [] });
    expect(container.firstChild).toBeNull();
  });

  it("names files by their basename, since the path is in the panel header", () => {
    draw();
    expect(screen.getByText("main.c")).toBeTruthy();
    expect(screen.getByText("util.c")).toBeTruthy();
  });

  it("marks which one is being read", () => {
    draw();
    const tabs = screen.getAllByRole("tab");
    expect(tabs[0].getAttribute("aria-selected")).toBe("true");
    expect(tabs[1].getAttribute("aria-selected")).toBe("false");
  });

  it("keeps the order files were opened in", () => {
    // A strip that re-sorts itself is one you have to re-read every time you
    // look at it.
    draw({ open: ["z.c", "a.c"], counts: new Map() });
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["z.c", "a.c"]);
  });
});

describe("what a tab says about its file", () => {
  it("carries the worst thing found in it, so it can be triaged unopened", () => {
    const { container } = draw();
    // The same dot the explorer draws, from the same `countByFile`.
    expect(container.querySelector('[title*="2건"]')).toBeTruthy();
  });

  it("says nothing when the file is clean", () => {
    const { container } = draw({ open: ["src/util.c"], counts: new Map() });
    expect(container.querySelector("[title]")).toBeNull();
  });

  it("shows a mark while it has unsaved text", () => {
    const { container } = draw({ dirty: ["src/main.c"] });
    expect(container.querySelector('[title="저장되지 않음"]')).toBeTruthy();
  });
});

describe("picking and closing", () => {
  it("asks for the file when a tab is pressed", async () => {
    const { onPick } = draw();
    await userEvent.click(screen.getByText("util.c"));
    expect(onPick).toHaveBeenCalledWith("src/util.c");
  });

  it("closes the one asked for, not the active one", async () => {
    const { onClose } = draw();
    await userEvent.click(screen.getByRole("button", { name: "src/util.c 닫기" }));
    expect(onClose).toHaveBeenCalledWith("src/util.c");
  });
});
