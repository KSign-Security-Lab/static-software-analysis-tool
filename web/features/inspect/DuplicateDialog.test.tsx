import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RunStatus, RunSummary, UploadResult } from "@/lib/api/types";

/**
 * "This code has been scanned before" — asked, rather than discovered afterwards.
 *
 * The offer depends on how the earlier run ended, and getting that wrong means
 * offering to resume something finished or to open something that never ran. The
 * other half is bookkeeping: taking the earlier run must delete the upload that
 * just happened, or 지난 검사 fills with unstarted duplicates of one tree.
 */

const startMatch = { mutateAsync: vi.fn().mockResolvedValue({}), isPending: false, reset: vi.fn() };
const startFresh = { mutateAsync: vi.fn().mockResolvedValue({}), isPending: false, reset: vi.fn() };
const resume = { mutateAsync: vi.fn().mockResolvedValue({}), isPending: false };
const remove = { mutateAsync: vi.fn().mockResolvedValue({}), isPending: false };

vi.mock("@/lib/run/queries", () => ({
  useStartRun: (runId: string) => (runId === "old" ? startMatch : startFresh),
  useDeleteRun: () => remove,
}));
vi.mock("@/lib/run/trace-queries", () => ({ useResume: () => resume }));
vi.mock("@/lib/run/stream", () => ({
  useRunStream: () => ({ ensureAttached: vi.fn().mockResolvedValue(undefined) }),
}));

afterEach(() => {
  for (const m of [startMatch, startFresh, resume, remove]) m.mutateAsync.mockClear();
  cleanup();
});

function match(status: RunStatus, over: Partial<RunSummary> = {}): RunSummary {
  return {
    run_id: "old",
    status,
    files: ["app.c"],
    file_count: 1,
    updated_at: Date.now() / 1000 - 600,
    started: true,
    origin: { kind: "zip", label: "proj.zip", url: null, ref: null, commit: null },
    ...over,
  };
}

async function show(m: RunSummary, others: RunSummary[] = []) {
  const { default: DuplicateDialog } = await import("./DuplicateDialog");
  const upload = {
    run_id: "fresh",
    uploaded: 1,
    index: { files_indexed: 1, files_skipped: 0, chunks: 2, links: 0 },
    files: ["app.c"],
    origin: { kind: "zip", label: "proj.zip", url: null, ref: null, commit: null },
    intake: { kept: 1, seen: 1, skipped: [] },
    matches: [m, ...others],
  } as UploadResult;
  const dismiss = vi.fn();
  const client = new QueryClient();
  render(
    <NuqsTestingAdapter searchParams={{}}>
      <QueryClientProvider client={client}>
        <DuplicateDialog upload={upload} onDismiss={dismiss} />
      </QueryClientProvider>
    </NuqsTestingAdapter>,
  );
  return dismiss;
}

describe("what it says", () => {
  it("names the earlier run and how it went", async () => {
    await show(match("done", { findings: 3 }));
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("proj.zip");
    expect(dialog.textContent).toContain("3건 발견");
  });

  it("mentions the others without listing them", async () => {
    await show(match("done"), [match("done", { run_id: "older" })]);
    expect(screen.getByRole("dialog").textContent).toContain("1건 더");
  });
});

describe("taking the earlier run", () => {
  it("opens a finished one without starting anything", async () => {
    const dismiss = await show(match("done"));
    await userEvent.click(screen.getByRole("button", { name: /그 결과 열기/ }));

    await waitFor(() => expect(remove.mutateAsync).toHaveBeenCalledWith("fresh"));
    expect(startMatch.mutateAsync).not.toHaveBeenCalled();
    expect(dismiss).not.toHaveBeenCalled();
  });

  it("carries on one that stopped part-way, without force", async () => {
    // `plan` skips every unit already marked inspected, so carrying on is cheap
    // -- and `force` would throw that away and redo the lot.
    await show(match("cancelled"));
    await userEvent.click(screen.getByRole("button", { name: /이어서 검사/ }));

    await waitFor(() => expect(startMatch.mutateAsync).toHaveBeenCalledWith({}));
  });

  it("uses the resume endpoint for a parked one", async () => {
    // `/inspect` would start a second worker beside the one still waiting.
    await show(match("interrupted"));
    await userEvent.click(screen.getByRole("button", { name: /이어서 검사/ }));

    await waitFor(() => expect(resume.mutateAsync).toHaveBeenCalledWith({ action: "resume" }));
    expect(startMatch.mutateAsync).not.toHaveBeenCalled();
  });

  it("starts one that was uploaded and never scanned", async () => {
    await show(match("indexed"));
    await userEvent.click(screen.getByRole("button", { name: /그 검사 시작/ }));
    await waitFor(() => expect(startMatch.mutateAsync).toHaveBeenCalledWith({}));
  });

  it("just watches one that is already running", async () => {
    await show(match("inspecting"));
    await userEvent.click(screen.getByRole("button", { name: /진행 중인 검사 보기/ }));

    await waitFor(() => expect(remove.mutateAsync).toHaveBeenCalledWith("fresh"));
    expect(startMatch.mutateAsync).not.toHaveBeenCalled();
    expect(resume.mutateAsync).not.toHaveBeenCalled();
  });

  it.each([
    ["done", /그 결과 열기/],
    ["failed", /이어서 검사/],
    ["indexed", /그 검사 시작/],
    ["inspecting", /진행 중인 검사 보기/],
  ] as const)("always deletes the upload that just happened (%s)", async (status, label) => {
    // It was never started and its tree is byte-identical to the one being
    // opened, so keeping it would fill 지난 검사 with duplicates of one thing.
    await show(match(status));
    await userEvent.click(screen.getByRole("button", { name: label }));

    await waitFor(() => expect(remove.mutateAsync).toHaveBeenCalledWith("fresh"));
  });
});

describe("scanning it again anyway", () => {
  it("starts the fresh run with force, and keeps it", async () => {
    // Without `force` this would re-serve the very cache the dialog just
    // described and finish in seconds having called no model.
    const dismiss = await show(match("done"));
    await userEvent.click(screen.getByRole("button", { name: /새로 검사/ }));

    await waitFor(() => expect(startFresh.mutateAsync).toHaveBeenCalledWith({ force: true }));
    expect(remove.mutateAsync).not.toHaveBeenCalled();
    await waitFor(() => expect(dismiss).toHaveBeenCalled());
  });
});
