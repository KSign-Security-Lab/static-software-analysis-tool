import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import DockTabs from "./DockTabs";

/**
 * The bottom panel's tab strip.
 *
 * 검사 drives it from the URL, because there the tab decides whether you are
 * looking at the problems, the pipeline or the call record -- all of which used
 * to be a full-window overlay, and all of which are worth linking someone to.
 * F2-A has one tab and leaves it alone. Both paths are asserted here: a
 * controllable component that quietly keeps its own state as well is how a strip
 * ends up showing one tab and reporting another.
 */

afterEach(cleanup);

const TABS = [
  { id: "problems", label: "문제", badge: 2, content: <p>list</p> },
  { id: "log", label: "기록", content: <p>record</p> },
  { id: "graph", label: "구조", content: <p>drawing</p> },
];

describe("uncontrolled", () => {
  it("opens on the first tab, so ordering says what matters", () => {
    render(<DockTabs tabs={TABS} />);
    expect(screen.getByText("list")).toBeTruthy();
    expect(screen.queryByText("record")).toBeNull();
  });

  it("switches on a click and keeps its own state", async () => {
    render(<DockTabs tabs={TABS} />);
    await userEvent.click(screen.getByRole("tab", { name: /기록/ }));
    expect(screen.getByText("record")).toBeTruthy();
    expect(screen.queryByText("list")).toBeNull();
  });
});

describe("controlled", () => {
  it("shows the tab it is given", () => {
    render(<DockTabs tabs={TABS} value="graph" onValueChange={() => {}} />);
    expect(screen.getByText("drawing")).toBeTruthy();
  });

  it("reports a click instead of acting on it", async () => {
    // The owner writes the URL and the URL comes back as `value`. If this also
    // moved by itself the strip could show one tab while the address bar named
    // another, and a reload would jump.
    const onValueChange = vi.fn();
    render(<DockTabs tabs={TABS} value="problems" onValueChange={onValueChange} />);

    await userEvent.click(screen.getByRole("tab", { name: /구조/ }));

    expect(onValueChange).toHaveBeenCalledWith("graph");
    expect(screen.getByText("list")).toBeTruthy();
  });

  it("falls back to the first tab when given one it does not have", () => {
    // `?panel=` can say anything. An empty panel would be worse than the default.
    render(<DockTabs tabs={TABS} value="nonsense" onValueChange={() => {}} />);
    expect(screen.getByText("list")).toBeTruthy();
  });
});

describe("what a tab carries", () => {
  it("mounts only the active tab", () => {
    // Two of 검사's five are React Flow canvases and one is a virtualized span
    // tree; keeping them alive means laying out graphs nobody can see.
    render(<DockTabs tabs={TABS} />);
    expect(screen.queryByText("record")).toBeNull();
    expect(screen.queryByText("drawing")).toBeNull();
  });

  it("shows a badge beside the label, and nothing where there is none", () => {
    render(<DockTabs tabs={TABS} />);
    // The count belongs on the tab so it is readable without opening it.
    expect(screen.getByRole("tab", { name: /문제/ }).textContent).toBe("문제2");
    expect(screen.getByRole("tab", { name: /기록/ }).textContent).toBe("기록");
  });
});
