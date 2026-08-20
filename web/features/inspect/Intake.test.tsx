import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, describe, expect, it, vi } from "vitest";

/**
 * Reading and parsing is not instant, and used to look like nothing.
 *
 * The upload response comes back *after* the server has chunked and linked the
 * whole tree -- indexing is synchronous so the next screen has a file list -- so
 * on a real project this is seconds during which the only sign of life was a
 * spinner inside one button, while the rest of the screen still invited another
 * folder. Dropping again there creates a second run and orphans the first.
 *
 * The mutations are stubbed rather than driven, because what is under test is
 * what the screen does *while* one is in flight.
 */

const pending = { isPending: true, mutateAsync: vi.fn(), mutate: vi.fn() };
const idle = { isPending: false, mutateAsync: vi.fn(), mutate: vi.fn() };

const state = { upload: idle, archive: idle, clone: idle };

vi.mock("@/lib/run/queries", () => ({
  useUpload: () => state.upload,
  useUploadArchive: () => state.archive,
  useCloneRepo: () => state.clone,
  useStartRun: () => idle,
  useAgentHealth: () => ({ data: { configured: true, base_url: "http://x", model: "agent" } }),
}));

afterEach(() => {
  state.upload = idle;
  state.archive = idle;
  state.clone = idle;
  cleanup();
});

async function show() {
  const { default: Intake } = await import("./Intake");
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <NuqsTestingAdapter searchParams={{}}>
      <QueryClientProvider client={client}>
        <Intake run={undefined} />
      </QueryClientProvider>
    </NuqsTestingAdapter>,
  );
}

describe("while nothing is in flight", () => {
  it("offers all three ways in", async () => {
    await show();
    expect(screen.getByRole("tab", { name: /폴더/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /압축 파일/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /git/ })).toBeInTheDocument();
  });
});

describe("while a tree is being read", () => {
  it("replaces the pickers rather than leaving them greyed", async () => {
    // A folder picker that is grey for an unstated reason is worse than one that
    // is gone and replaced by what is actually happening.
    state.upload = pending;
    await show();

    expect(screen.getByText("코드를 읽는 중")).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /폴더/ })).toBeNull();
  });

  it("says what the wait is for", async () => {
    state.upload = pending;
    await show();
    expect(screen.getByText(/함수 단위로 쪼개/)).toBeInTheDocument();
  });

  it("distinguishes a clone, which is the slow one", async () => {
    state.clone = pending;
    await show();
    expect(screen.getByText("저장소를 가져오는 중")).toBeInTheDocument();
  });

  it("covers an archive too", async () => {
    state.archive = pending;
    await show();
    expect(screen.getByText("코드를 읽는 중")).toBeInTheDocument();
  });
});
