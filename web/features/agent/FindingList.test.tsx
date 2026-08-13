import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import type { Span, UiFinding } from "@/lib/model/finding";
import FindingList from "./FindingList";

/**
 * A finding, and the argument under it.
 *
 * The assertions that matter here are about navigation: a finding is a claim
 * about several lines in several files, and every one of those lines used to
 * open the file and land on the claim's own line instead of its own.
 */

afterEach(cleanup);

// Opening a row scrolls it to the top of the dock, and jsdom has no scrolling.
beforeAll(() => {
  Element.prototype.scrollIntoView = vi.fn();
});

const span =(file: string, line: number): Span => ({
  file,
  startLine: line,
  startColumn: 1,
  endLine: line,
  endColumn: 1,
  excerpt: "",
});

const FINDING: UiFinding = {
  id: "f1",
  engine: "agent",
  chunkId: "net.c::handle",
  severity: "high",
  title: "명령어 주입 가능",
  cwe: "CWE-78",
  primary: span("net.c", 41),
  explanation: "URL이 검사 없이 셸로 넘어갑니다.",
  evidence: [
    { role: "source", span: span("http.c", 12), note: "요청에서 그대로 읽습니다" },
    { role: "propagation", span: span("net.c", 30), note: "버퍼로 복사됩니다" },
    { role: "sink", span: span("net.c", 41), note: "system() 으로 실행됩니다" },
  ],
  replacement: null,
  remediation: "인자를 배열로 넘기세요.",
  diff: null,
  confidence: 0.85,
  verified: true,
  raw: {} as UiFinding["raw"],
};

function draw(overrides: Partial<React.ComponentProps<typeof FindingList>> = {}) {
  const onNavigate = vi.fn();
  const onOpen = vi.fn();
  render(
    <FindingList
      findings={[FINDING]}
      openId={null}
      onOpen={onOpen}
      onNavigate={onNavigate}
      emptyHint="아무것도 없습니다"
      {...overrides}
    />,
  );
  return { onNavigate, onOpen };
}

describe("opening a finding", () => {
  it("navigates to the line the claim is filed under", async () => {
    const { onNavigate, onOpen } = draw();
    await userEvent.click(screen.getByRole("button", { name: /명령어 주입 가능/ }));

    expect(onOpen).toHaveBeenCalledWith(FINDING);
    expect(onNavigate).toHaveBeenCalledWith("net.c", 41);
  });
});

describe("walking the evidence trail", () => {
  it("sends each step's own file and line, not the claim's", async () => {
    // The bug this covers: the trail crosses files, and every step used to
    // arrive at the finding's primary line because the line was dropped.
    const { onNavigate } = draw({ openId: "f1" });

    await userEvent.click(screen.getByRole("button", { name: /요청에서 그대로 읽습니다/ }));
    expect(onNavigate).toHaveBeenLastCalledWith("http.c", 12);

    await userEvent.click(screen.getByRole("button", { name: /버퍼로 복사됩니다/ }));
    expect(onNavigate).toHaveBeenLastCalledWith("net.c", 30);
  });

  it("labels each step by its role", () => {
    draw({ openId: "f1" });
    for (const label of ["유입", "전파", "위험 지점"]) {
      expect(screen.getByText(label)).toBeTruthy();
    }
  });
});

describe("the grounds", () => {
  it("keeps the fix out of the columns, where it has room for a patch", () => {
    // 판단 and 근거 read as prose and sit side by side. The fix holds a patch,
    // and a patch in a third of the dock scrolled sideways to show a line that
    // would have fitted whole -- while 근거, two sentences long, reserved another
    // third and left it empty to the bottom of the tallest column.
    draw({ openId: "f1" });
    for (const heading of ["판단", "근거", "고치는 방법"]) {
      expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
    }
    const fix = screen.getByRole("heading", { name: "고치는 방법" }).closest("section")!;
    const claim = screen.getByRole("heading", { name: "판단" }).closest("section")!;
    expect(fix.parentElement).not.toBe(claim.parentElement);
  });

  it("says the confidence once, on the badge", () => {
    // It was on a meter as well, three lines under a badge that had just said
    // `취약 확인 · 95%` -- the same number twice, in two shapes.
    draw({ openId: "f1" });

    expect(screen.getAllByText(/\d+%/)).toHaveLength(1);
    expect(screen.queryByRole("meter")).toBeNull();
  });

  it("says nothing about a fix when there is none to suggest", () => {
    draw({ findings: [{ ...FINDING, remediation: null }], openId: "f1" });
    expect(screen.queryByRole("heading", { name: "고치는 방법" })).toBeNull();
  });
});

describe("against another run", () => {
  const compare = { fresh: new Set(["f1"]), fixed: [{ ...FINDING, id: "f0", title: "지난 실행의 문제" }] };

  it("marks what this run added and what the last one had", async () => {
    draw({ compare });
    expect(screen.getByText("새로")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: /해결됨 1건/ }));
    expect(screen.getByText("지난 실행의 문제")).toBeTruthy();
  });

  it("calls a carried-over finding what it is", () => {
    draw({ compare: { fresh: new Set<string>(), fixed: [] } });
    expect(screen.getByText("그대로")).toBeTruthy();
  });
});
