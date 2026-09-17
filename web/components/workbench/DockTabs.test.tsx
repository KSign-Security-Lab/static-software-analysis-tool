import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import DockTabs from "./DockTabs";

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
    const onValueChange = vi.fn();
    render(<DockTabs tabs={TABS} value="problems" onValueChange={onValueChange} />);

    await userEvent.click(screen.getByRole("tab", { name: /구조/ }));

    expect(onValueChange).toHaveBeenCalledWith("graph");
    expect(screen.getByText("list")).toBeTruthy();
  });

  it("falls back to the first tab when given one it does not have", () => {
    render(<DockTabs tabs={TABS} value="nonsense" onValueChange={() => {}} />);
    expect(screen.getByText("list")).toBeTruthy();
  });
});

describe("what a tab carries", () => {
  it("mounts only the active tab", () => {
    render(<DockTabs tabs={TABS} />);
    expect(screen.queryByText("record")).toBeNull();
    expect(screen.queryByText("drawing")).toBeNull();
  });

  it("shows a badge beside the label, and nothing where there is none", () => {
    render(<DockTabs tabs={TABS} />);
    expect(screen.getByRole("tab", { name: /문제/ }).textContent).toBe("문제2");
    expect(screen.getByRole("tab", { name: /기록/ }).textContent).toBe("기록");
  });
});
