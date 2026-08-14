import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { RunSummary } from "@/lib/api/types";
import { keys } from "@/lib/query/keys";
import RunHistory from "./RunHistory";

/**
 * The scans this server still has, and how to be rid of them.
 *
 * Worth covering because it is the one destructive control on the surface and
 * because `전체 지우기` is a *loop*: the server deletes one run per request and
 * has no bulk endpoint, so the things that can go wrong are the things that go
 * wrong with loops -- deleting the wrong member, stopping early, or letting the
 * dialog close while it is still running.
 *
 * `deleteRun` is stubbed rather than the fetch layer, because what is being
 * asserted is which runs get deleted and in what order, not how a DELETE is
 * spelled.
 */

const deleteRun = vi.hoisted(() => vi.fn(async (id: string) => ({ deleted: id })));

vi.mock("@/lib/api/runs", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/runs")>()),
  deleteRun,
}));
vi.mock("next/navigation", () => ({ usePathname: () => "/agent" }));

afterEach(cleanup);
beforeEach(() => deleteRun.mockClear());

const CURRENT = "run-current";

function run(over: Partial<RunSummary> & { run_id: string }): RunSummary {
  return {
    status: "done",
    files: ["main.c"],
    file_count: 1,
    updated_at: 1_786_586_840,
    started: true,
    findings: 3,
    ...over,
  };
}

const RUNS: RunSummary[] = [
  run({ run_id: CURRENT, findings: 3 }),
  run({ run_id: "run-a", files: ["util.c"], findings: 1 }),
  run({ run_id: "run-b", files: ["net.c"], file_count: 2, started: false, findings: undefined }),
];

function show(runs = RUNS) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(keys.runs(), runs);
  return render(
    <NuqsTestingAdapter searchParams={{ run: CURRENT }}>
      <QueryClientProvider client={client}>
        <RunHistory />
      </QueryClientProvider>
    </NuqsTestingAdapter>,
  );
}

/**
 * The trigger names the run it is on, so that is what it is found by.
 *
 * It used to read `지난 검사 3` -- a count, on the one permanently visible
 * control that could have been saying which run the whole surface was showing.
 */
const trigger = () => screen.getByRole("button", { name: /main\.c/ });
const open = () => userEvent.click(trigger());

describe("the run it is on", () => {
  it("names it, because nothing else on the surface does", () => {
    // `?run=` is what the report, the trace and every finding hang off, and no
    // pixel said which one it was.
    show();
    expect(trigger().textContent).toContain("main.c");
  });

  it("says so when there is no run at all", () => {
    show([]);
    expect(screen.getByRole("button", { name: /검사 없음/ })).toBeTruthy();
  });
});

describe("the list", () => {
  it("counts what the server has, at the head of the list it counts", async () => {
    show();
    await open();
    expect(screen.getByText("지난 검사 3")).toBeTruthy();
  });

  it("marks the run on screen, and gives it no way to be deleted", async () => {
    // Deleting what you are looking at is a different act from tidying history,
    // and it has its own control in the explorer.
    show();
    await open();

    expect(screen.getByText("보는 중")).toBeTruthy();
    expect(screen.queryByRole("button", { name: `${CURRENT} 검사 지우기` })).toBeNull();
    expect(screen.getByRole("button", { name: /util.c 검사 지우기/ })).toBeTruthy();
  });

  it("says a run was never inspected rather than calling it clean", async () => {
    // `0건` on a run nothing ever scanned reads as "no problems found", which is
    // the opposite of what it means.
    show();
    await open();
    expect(screen.getByText("검사 안 함")).toBeTruthy();
  });

  it("names a run by its files, since nobody recognises a run id", async () => {
    show();
    await open();
    expect(screen.getByText("net.c 외 1")).toBeTruthy();
  });

  it("says so when there is nothing kept", async () => {
    show([]);
    await userEvent.click(screen.getByRole("button", { name: /검사 없음/ }));
    expect(screen.getByText("아직 검사한 기록이 없습니다.")).toBeTruthy();
  });
});

describe("deleting one", () => {
  it("deletes just that run", async () => {
    show();
    await open();
    await userEvent.click(screen.getByRole("button", { name: /util.c 검사 지우기/ }));

    // The id, not the whole call: react-query hands the mutation a context
    // object as a second argument, which is not what is being asserted.
    expect(deleteRun).toHaveBeenCalledTimes(1);
    expect(deleteRun.mock.calls[0][0]).toBe("run-a");
  });
});

describe("전체 지우기", () => {
  it("asks before doing anything", async () => {
    show();
    await open();
    await userEvent.click(screen.getByRole("button", { name: "전체 지우기" }));

    expect(screen.getByText(/지울까요\?/)).toBeTruthy();
    expect(deleteRun).not.toHaveBeenCalled();
  });

  it("deletes nothing when the reader backs out", async () => {
    show();
    await open();
    await userEvent.click(screen.getByRole("button", { name: "전체 지우기" }));
    await userEvent.click(screen.getByRole("button", { name: "그만두기" }));

    expect(deleteRun).not.toHaveBeenCalled();
  });

  it("spares the run on screen, and says so before it starts", async () => {
    show();
    await open();
    await userEvent.click(screen.getByRole("button", { name: "전체 지우기" }));

    // The count in the question is the count it will actually delete.
    expect(screen.getByText("지난 검사 2개를 지울까요?")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: "지우기" }));

    await waitFor(() => expect(deleteRun).toHaveBeenCalledTimes(2));
    const deleted = deleteRun.mock.calls.map(([id]) => id);
    expect(deleted).toEqual(["run-a", "run-b"]);
    expect(deleted).not.toContain(CURRENT);
  });

  it("deletes one at a time rather than firing them all at once", async () => {
    // Directory removals against a local server: doing them together buys
    // nothing worth the failure modes.
    let open_calls = 0;
    let peak = 0;
    deleteRun.mockImplementation(async (id: string) => {
      open_calls += 1;
      peak = Math.max(peak, open_calls);
      await new Promise((r) => setTimeout(r, 5));
      open_calls -= 1;
      return { deleted: id };
    });

    show();
    await open();
    await userEvent.click(screen.getByRole("button", { name: "전체 지우기" }));
    await userEvent.click(screen.getByRole("button", { name: "지우기" }));

    await waitFor(() => expect(deleteRun).toHaveBeenCalledTimes(2));
    expect(peak).toBe(1);
  });

  it("does not offer to clear a history that is only the current run", async () => {
    show([RUNS[0]]);
    await open();
    expect(screen.queryByRole("button", { name: "전체 지우기" })).toBeNull();
  });
});
