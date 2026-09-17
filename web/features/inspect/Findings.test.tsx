import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { RunStreamProvider } from "@/lib/run/stream";
import { resetAll } from "@/lib/inspect/bucket";
import type { UiFinding } from "@/lib/model/finding";
import { keys } from "@/lib/query/keys";
import Findings from "./Findings";

const RUN = "r1";

afterEach(cleanup);
beforeEach(() => {
  resetAll();
  window.sessionStorage.clear();
});

function finding(over: Partial<UiFinding> & { id: string }): UiFinding {
  return {
    engine: "agent",
    chunkId: null,
    severity: "medium",
    title: `문제 ${over.id}`,
    cwe: null,
    primary: { file: "a.c", startLine: 1, startColumn: 1, endLine: 1, endColumn: 1, excerpt: "" },
    explanation: "",
    evidence: [],
    remediation: null,
    replacement: "x",
    diff: null,
    chunkIds: [],
    mergedIds: [],
    confidence: 0.5,
    verified: true,
    reach: null,
    raw: {} as UiFinding["raw"],
    ...over,
  };
}

function show(findings: UiFinding[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  client.setQueryData(keys.findings(RUN), { schema_version: "1", run_id: RUN, findings: [], stats: {} });
  client.setQueryData(keys.summary(RUN), { run_id: RUN, status: "done", files: [], file_count: 0, updated_at: 0, started: true });
  return render(
    <NuqsTestingAdapter searchParams={{ run: RUN }}>
      <QueryClientProvider client={client}>
        <RunStreamProvider runId={null}>
          <Findings findings={findings} />
        </RunStreamProvider>
      </QueryClientProvider>
    </NuqsTestingAdapter>,
  );
}

const ROWS = [
  finding({ id: "crit", severity: "critical", cwe: "CWE-78" }),
  finding({ id: "low-a", severity: "low", cwe: "CWE-78" }),
  finding({ id: "low-b", severity: "low", cwe: "CWE-476" }),
];

describe("an empty report", () => {
  it("says nothing was found rather than showing an empty table", () => {
    show([]);
    expect(screen.getByText("찾은 취약점이 없습니다")).toBeInTheDocument();
  });
});

describe("the list", () => {
  it("puts the worst first by default", () => {
    show(ROWS);
    const titles = screen.getAllByRole("button").map((b) => b.textContent ?? "");
    expect(titles.find((t) => t.includes("문제 crit"))).toBeTruthy();
    const all = screen.getByRole("list").textContent ?? "";
    expect(all.indexOf("문제 crit")).toBeLessThan(all.indexOf("문제 low-a"));
  });

  it("counts every row, not just the visible ones", () => {
    show(ROWS);
    expect(screen.getByText("3건")).toBeInTheDocument();
  });
});

describe("filtering", () => {
  it("narrows the rows and says how many of how many are left", async () => {
    show(ROWS);
    await userEvent.click(screen.getByRole("button", { name: "치명적만 보기" }));

    const list = screen.getByRole("list").textContent ?? "";
    expect(list).toContain("문제 crit");
    expect(list).not.toContain("문제 low-a");
    expect(screen.getByText("1 / 3")).toBeInTheDocument();
  });

  it("leaves the facet counts alone while filtering", async () => {
    show(ROWS);
    await userEvent.click(screen.getByRole("button", { name: "치명적만 보기" }));
    expect(screen.getByRole("button", { name: "낮음만 보기" }).textContent).toContain("2");
  });

  it("says so when a combination matches nothing", async () => {
    show(ROWS);
    await userEvent.click(screen.getByRole("button", { name: "치명적만 보기" }));
    await userEvent.click(screen.getByRole("button", { name: "CWE-476만 보기" }));
    expect(screen.getByText(/이 조건에 맞는 것이 없습니다/)).toBeInTheDocument();
  });

  it("offers a way back out of a filter", async () => {
    show(ROWS);
    await userEvent.click(screen.getByRole("button", { name: "치명적만 보기" }));
    await userEvent.click(screen.getByRole("button", { name: "조건 지우기" }));
    expect(screen.getByText("3건")).toBeInTheDocument();
  });
});

describe("the bucket tray", () => {
  it("stays away until something is ticked", () => {
    show(ROWS);
    expect(screen.queryByText(/담김/)).toBeNull();
  });

  it("appears with a count once a row is ticked", async () => {
    show(ROWS);
    await userEvent.click(screen.getAllByRole("checkbox")[1]);
    expect(screen.getByText(/1건/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /패치 만들기/ })).toBeInTheDocument();
  });

  it("names how many of the ticks carry no code", async () => {
    show([...ROWS, finding({ id: "prose", replacement: null })]);
    await userEvent.click(screen.getByRole("checkbox", { name: /문제 prose/ }));
    expect(screen.getByText(/패치 없는 것/)).toBeInTheDocument();
  });
});

describe("code that does not run", () => {
  const reach = (state: string, why: string[] = []) =>
    ({ state, callers: 0, hops: null, why }) as UiFinding["reach"];

  function mixed() {
    return [
      finding({ id: "1", title: "살아 있는 것" }),
      finding({ id: "2", title: "도달 못 하는 것", reach: reach("unreachable", ["파일 밖에서 부를 수 없는 선언"]) }),
      finding({ id: "3", title: "시험 코드", reach: reach("excluded") }),
    ];
  }

  it("keeps the reachable ones in front and folds the rest away", async () => {
    show(mixed());

    expect(await screen.findByText("살아 있는 것")).toBeTruthy();
    expect(screen.queryByText("도달 못 하는 것")).toBeNull();
    expect(screen.queryByText("시험 코드")).toBeNull();
  });

  it("says how many it folded, rather than quietly dropping them", async () => {
    show(mixed());
    expect(await screen.findByText(/트리에서 도달 불가 2건/)).toBeTruthy();
  });

  it("shows them on one click", async () => {
    show(mixed());
    await userEvent.click(await screen.findByText(/트리에서 도달 불가 2건/));

    expect(screen.getByText("도달 못 하는 것")).toBeTruthy();
    expect(screen.getByText("시험 코드")).toBeTruthy();
  });

  it("does not fold away the very thing a reader just asked to see", async () => {
    show(mixed());
    await userEvent.click(await screen.findByText("도달 불가"));

    expect(screen.getByText("도달 못 하는 것")).toBeTruthy();
    expect(screen.queryByText(/트리에서 도달 불가 2건/)).toBeNull();
  });

  it("counts every finding in the facets, folded or not", async () => {
    show(mixed());
    expect(await screen.findByText("도달 불가")).toBeTruthy();
    expect(screen.getByText("시험·예제 코드")).toBeTruthy();
  });
});
