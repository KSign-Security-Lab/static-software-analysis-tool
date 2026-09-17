import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RunStats } from "@/lib/api/types";

const start = { mutate: vi.fn(), isPending: false };
vi.mock("@/lib/run/queries", () => ({ useStartRun: () => start }));
vi.mock("@/lib/run/stream", () => ({ useRunStream: () => ({ ensureAttached: vi.fn() }) }));

let spans: unknown[] = [];
vi.mock("@/lib/run/trace-queries", () => ({ useSpans: () => ({ data: { spans } }) }));

afterEach(() => {
  start.mutate.mockReset();
  spans = [];
  cleanup();
});

function failedSpan(name: string) {
  return { id: name, name, kind: "llm", status: "error", error: "length limit" };
}

async function show(stats: Partial<RunStats> | undefined) {
  const { default: Coverage } = await import("./Coverage");
  const client = new QueryClient();
  return render(
    <NuqsTestingAdapter searchParams={{ run: "r1" }}>
      <QueryClientProvider client={client}>
        <Coverage stats={stats as RunStats} />
      </QueryClientProvider>
    </NuqsTestingAdapter>,
  );
}

describe("a scan that did all its own work", () => {
  it("says nothing at all", async () => {
    await show({ failed: 0, chunks_cached: 0, chunks_inspected: 4 });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByText(/지난 검사 결과/)).toBeNull();
  });

  it("says nothing when there are no stats yet", async () => {
    await show(undefined);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("judgements that failed", () => {
  it("says the units were not read, not that they were clean", async () => {
    await show({ failed: 14, chunks_inspected: 46 });
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("14번");
    expect(alert.textContent).toContain("없다는 뜻이 아니라 못 봤다는 뜻");
  });

  it("names the lever that actually moves it", async () => {
    await show({ failed: 1 });
    expect(screen.getByRole("alert").textContent).toContain("다시 검사를 돌리면");
  });
});

describe("units served from an earlier run", () => {
  it("says so, because a five-second scan reads as having resumed something", async () => {
    await show({ chunks_cached: 2, chunks_inspected: 0 });
    expect(screen.getByText(/모델을 부르지 않았습니다/)).toBeInTheDocument();
  });

  it("distinguishes a partially warm run from a wholly warm one", async () => {
    await show({ chunks_cached: 40, chunks_inspected: 3 });
    expect(screen.queryByText(/모델을 부르지 않았습니다/)).toBeNull();
    expect(screen.getByText(/3개만 새로 읽었습니다/)).toBeInTheDocument();
  });

  it("explains why those units have no 판단 과정", async () => {
    await show({ chunks_cached: 2, chunks_inspected: 0 });
    expect(screen.getByText(/호출이 일어나지 않았기 때문입니다/)).toBeInTheDocument();
  });

  it("offers a re-scan that turns the reuse off", async () => {
    await show({ chunks_cached: 2, chunks_inspected: 0 });
    screen.getByRole("button", { name: /전체 다시 검사/ }).click();
    expect(start.mutate).toHaveBeenCalledWith({ force: true });
  });
});

describe("both at once", () => {
  it("keeps them apart, because one is a warning and one is not", async () => {
    await show({ failed: 3, chunks_cached: 5, chunks_inspected: 1 });
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/지난 검사 결과를 그대로 가져왔고/)).toBeInTheDocument();
  });
});

describe("which units were not fully read", () => {
  it("names the unit and the lens that died", async () => {
    spans = [failedSpan("lens:memory:bn_Add"), failedSpan("lens:logic:EN_Mul")];
    await show({ failed: 2 });

    expect(screen.getByText(/끝까지 읽지 못한 단위/).textContent).toContain("2개");
    expect(screen.getByText("bn_Add")).toBeTruthy();
    expect(screen.getByText("EN_Mul")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("memory 분석");
  });

  it("does not count a call that a retry made good", async () => {
    spans = [failedSpan("lens:memory:bn_Add"), { id: "2", name: "lens:memory:bn_Add", kind: "llm", status: "ok" }];
    await show({ failed: 1 });

    expect(screen.queryByText(/끝까지 읽지 못한 단위/)).toBeNull();
  });

  it("says nothing extra when the trace has not arrived", async () => {
    spans = [];
    await show({ failed: 3 });

    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.queryByText(/끝까지 읽지 못한 단위/)).toBeNull();
  });
});
