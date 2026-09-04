import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RunStatus, RunSummary } from "@/lib/api/types";
import { IDLE, type RunLive } from "@/lib/run/reduce";

/**
 * The strip has three faces, and it used to have one.
 *
 * Its *mount* carried the meaning "something is happening", so a stopped run
 * lost it -- along with the only 이어서 and 중단 on the surface. `Intake` owns
 * 검사 시작 and never renders on results, so a stop was a dead end for the run
 * it stopped.
 */

const cancel = { mutate: vi.fn(), isPending: false };
const start = { mutate: vi.fn(), isPending: false };
const resume = { mutate: vi.fn(), isPending: false };

let live: RunLive = IDLE;
let row: RunSummary | undefined;

vi.mock("@/lib/inspect/queries", () => ({ useCancelRun: () => cancel }));
vi.mock("@/lib/run/trace-queries", () => ({ useResume: () => resume, useSpans: () => ({ data: { spans: [] } }) }));
vi.mock("@/lib/run/stream", () => ({ useRunStream: () => ({ live, ensureAttached: vi.fn() }) }));
vi.mock("@/lib/run/queries", () => ({ useRun: () => ({ data: row }), useStartRun: () => start }));

afterEach(() => {
  cancel.mutate.mockReset();
  start.mutate.mockReset();
  resume.mutate.mockReset();
  live = IDLE;
  row = undefined;
  cleanup();
});

function run(status: RunStatus): RunSummary {
  return { run_id: "r1", status, files: ["app.c"], file_count: 1, updated_at: 0, started: true };
}

async function show(status: RunStatus, over: Partial<RunLive> = {}) {
  row = run(status);
  live = { ...IDLE, ...over };
  const { default: ScanStrip } = await import("./ScanStrip");
  return render(
    <NuqsTestingAdapter searchParams={{ run: "r1" }}>
      <QueryClientProvider client={new QueryClient()}>
        <ScanStrip />
      </QueryClientProvider>
    </NuqsTestingAdapter>,
  );
}

describe("a scan in flight", () => {
  it("says what it is doing", async () => {
    await show("inspecting", { active: true, attached: true, running: ["verify"] });

    expect(screen.getByText("반박해 보는 중")).toBeTruthy();
    expect(screen.getByRole("button", { name: /중단/ })).toBeTruthy();
  });

  it("says the connection dropped rather than spinning through it", async () => {
    // Not attached is not the same as not running. The last frame received used
    // to sit on screen under a spinner as though it were current.
    await show("inspecting", { active: true, attached: false });

    expect(screen.getByText(/연결이 끊겼습니다/)).toBeTruthy();
  });

  it("offers no second stop while one is outstanding", async () => {
    await show("inspecting", { active: true, attached: true, cancelling: true });

    const button = screen.getByRole("button", { name: /중단하는 중/ }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
  });
});

describe("a scan that stopped short", () => {
  it("offers a way to carry a cancelled run on, and a way to redo it", async () => {
    await show("cancelled");

    expect(screen.getByText("중단했습니다")).toBeTruthy();
    screen.getByRole("button", { name: /이어서 검사/ }).click();
    // `/inspect` is the resume for a cancelled run: chunk ids are content
    // derived, so what it left undone is exactly what `uninspected()` returns.
    expect(start.mutate).toHaveBeenCalledWith({});
    expect(resume.mutate).not.toHaveBeenCalled();

    screen.getByRole("button", { name: /전체 다시 검사/ }).click();
    expect(start.mutate).toHaveBeenLastCalledWith({ force: true });
  });

  it("resumes a parked run from its checkpoint instead", async () => {
    // `/inspect` would not do: the worker is waiting to be told what to do, and
    // the checkpoint is the whole point of having stopped there.
    await show("interrupted");

    expect(screen.getByText("중단점에서 멈춰 있습니다")).toBeTruthy();
    screen.getByRole("button", { name: /이어서 검사/ }).click();
    expect(resume.mutate).toHaveBeenCalledWith({ action: "resume" });
    expect(start.mutate).not.toHaveBeenCalled();
  });

  it("does not offer to stop what has already stopped", async () => {
    await show("cancelled");
    expect(screen.queryByRole("button", { name: /^중단$/ })).toBeNull();
  });
});
