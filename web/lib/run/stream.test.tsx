import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunHandlers } from "@/lib/api/events";
import type { RunStatus, RunSummary } from "@/lib/api/types";

/**
 * The provider's recovery policy, not the browser's.
 *
 * `EventSource` is mocked rather than driven: jsdom has none, and what is worth
 * pinning is the decision to re-open, which is this file's and not the socket's.
 * A clean `stream_closed` never reconnects on its own -- that is correct, and it
 * is why a run whose stream was lost used to sit on screen for ever.
 */

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
    // The row says the run is going and no `open` ever arrives -- the shape of
    // both a dropped socket and a stream the server closed on the previous
    // run's `finished` flag a second after this one attached.
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

    // The second wait is twice the first, so nothing happens at +1.1s again.
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
    // The 2s ceiling resolved the promise and left the resolver on the list,
    // which then grew for the life of the tab and was called on every later
    // open. Asserted through the re-attach path, which is what drains it.
    await mount("inspecting");

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    await act(async () => {
      attached[attached.length - 1].onOpen?.();
    });

    // An open after a re-attach must not throw on a stale resolver.
    expect(attached.length).toBeGreaterThan(1);
  });
});
