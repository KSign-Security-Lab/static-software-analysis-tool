import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TooltipProvider } from "@/components/ui/tooltip";
import { IDLE, type RunLive } from "@/lib/run/reduce";
import { Alerts, Phase } from "./RunBar";

/**
 * The parts of the run bar that say something is happening.
 *
 * These used to be `RunPane`'s status strip, and were asserted in
 * `RunPane.test.tsx`. They moved with the fact: phase and stream health are
 * true of the whole run, not of one reading of it.
 *
 * The bar itself pulls five queries and two providers, so what is exercised
 * here is the two pieces that hold the logic. Everything else in it is a
 * button wired to a mutation.
 */

afterEach(cleanup);

const live = (over: Partial<RunLive> = {}): RunLive => ({ ...IDLE, ...over });

function show(node: React.ReactNode) {
  // The app mounts one in `app/providers.tsx`; the harness has to as well or
  // the running-nodes tooltip throws rather than rendering.
  return render(<TooltipProvider>{node}</TooltipProvider>);
}

describe("Phase", () => {
  it("reports what is running by its node name, deduplicated", () => {
    // Four verifiers in flight is one activity, not four.
    show(<Phase phase="running" live={live({ running: ["injection", "injection", "verify"] })} />);

    expect(screen.getByText("검사 중")).toBeTruthy();
    expect(screen.getByText("injection, verify")).toBeTruthy();
  });

  it("names the resting states rather than going quiet", () => {
    show(<Phase phase="finished" live={live()} />);
    expect(screen.getByText("검사 완료")).toBeTruthy();

    cleanup();
    show(<Phase phase="failed" live={live()} />);
    expect(screen.getByText("검사 실패")).toBeTruthy();

    cleanup();
    show(<Phase phase="paused" live={live()} />);
    expect(screen.getByText("중단점에서 멈춤")).toBeTruthy();
  });

  it("says a run has not happened yet, rather than nothing at all", () => {
    show(<Phase phase="idle" live={live()} />);
    expect(screen.getByText("검사 전")).toBeTruthy();
  });

  it("does not name a node when there is no run to be in one", () => {
    show(<Phase phase="finished" live={live({ running: ["verify"] })} />);
    expect(screen.queryByText("verify")).toBeNull();
  });
});

describe("Alerts", () => {
  it("says when the event stream dropped, rather than looking stuck", () => {
    show(<Alerts live={live({ active: true, attached: false })} />);
    expect(screen.getByText("연결 끊김 · 다시 연결 중")).toBeTruthy();
  });

  it("keeps quiet about a stream that is simply not running", () => {
    // Not attached and not active is an idle tab, not a dropped connection.
    show(<Alerts live={live({ active: false, attached: false })} />);
    expect(screen.queryByText("연결 끊김 · 다시 연결 중")).toBeNull();
  });

  it("shows a refusal and a run error together, since they are different failures", () => {
    show(<Alerts live={live({ refusal: "상태를 바꿀 수 없습니다" })} error="인덱싱에 실패했습니다" />);
    expect(screen.getByText("상태를 바꿀 수 없습니다")).toBeTruthy();
    expect(screen.getByText("인덱싱에 실패했습니다")).toBeTruthy();
  });

  it("renders nothing when the run is healthy", () => {
    const { container } = show(<Alerts live={live()} />);
    expect(container.textContent).toBe("");
  });
});
