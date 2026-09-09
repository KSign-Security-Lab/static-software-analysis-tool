import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunHandlers } from "@/lib/api/events";
import type { RunStatus, RunSummary } from "@/lib/api/types";

const attached: RunHandlers[] = [];
const closers: ReturnType<typeof vi.fn>[] = [];

vi.mock("@/lib/api/events", () => ({
  watchRun: (_id: string, handlers: RunHandlers) => {
    attached.push(handlers);
    const close = vi.fn();
    closers.push(close);
    return close;
  },
}));

let row: RunSummary | undefined;
vi.mock("@/lib/run/queries", () => ({ useRun: () => ({ data: row }) }));

function run(status: RunStatus): RunSummary {
  return { run_id: "r1", status, files: ["app.c"], file_count: 1, updated_at: 0, started: true };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  attached.length = 0;
  closers.length = 0;
  row = undefined;
  cleanup();
});

async function mount(status: RunStatus) {
  row = run(status);
  const { RunStreamProvider } = await import("./stream");
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <RunStreamProvider runId="r1">
        <div />
      </RunStreamProvider>
    </QueryClientProvider>,
  );
}

describe("a scan the tab is not attached to", () => {
  it("re-opens the stream rather than waiting to be told", async () => {
    await mount("inspecting");
    expect(attached).toHaveLength(1);

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(attached.length).toBeGreaterThan(1);
  });

  it("backs off, because the usual reason is a server that is not there", async () => {
    await mount("inspecting");

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    const afterFirst = attached.length;

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(attached).toHaveLength(afterFirst);

    await act(async () => {
      vi.advanceTimersByTime(1000);
    });
    expect(attached.length).toBeGreaterThan(afterFirst);
  });

  it("stops once the stream is open", async () => {
    await mount("inspecting");

    await act(async () => {
      attached[0].onOpen?.();
    });
    await act(async () => {
      vi.advanceTimersByTime(20_000);
    });

    expect(attached).toHaveLength(1);
  });
});

describe("a run that is not going", () => {
  it("is left alone", async () => {
    await mount("done");

    await act(async () => {
      vi.advanceTimersByTime(20_000);
    });
    expect(attached).toHaveLength(1);
  });
});

describe("ensureAttached", () => {
  it("does not leave its waiter behind when the ceiling wins", async () => {
    await mount("inspecting");

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    await act(async () => {
      attached[attached.length - 1].onOpen?.();
    });

    expect(attached.length).toBeGreaterThan(1);
  });
});
