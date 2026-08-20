import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { resetAll } from "@/lib/inspect/bucket";
import type { UiFinding } from "@/lib/model/finding";
import { keys } from "@/lib/query/keys";
import Findings from "./Findings";

/**
 * The report as a working list.
 *
 * What is worth pinning here is not the rendering -- `FindingRow` covers that --
 * but the two behaviours that make the list usable on a real scan: the facet
 * counts are over the whole report rather than over what is currently shown, and
 * an empty report is a result rather than an error.
 *
 * A run *is* in the URL, because the bucket is keyed by it and no run means no
 * ticks. The queries it enables are seeded into the cache instead of mocked, so
 * nothing reaches the network and nothing has to pretend to be `fetch`.
 */

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
    raw: {} as UiFinding["raw"],
    ...over,
  };
}

function show(findings: UiFinding[]) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  // Seeded, not stubbed: the components read through the same hooks they do in
  // the app, and a cache hit is indistinguishable from a served response.
  client.setQueryData(keys.findings(RUN), { schema_version: "1", run_id: RUN, findings: [], stats: {} });
  client.setQueryData(keys.summary(RUN), { run_id: RUN, status: "done", files: [], file_count: 0, updated_at: 0, started: true });
  return render(
    <NuqsTestingAdapter searchParams={{ run: RUN }}>
      <QueryClientProvider client={client}>
        <Findings findings={findings} />
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
    // The critical row precedes both low ones in the DOM.
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
    // A control whose number changes when you press it cannot say what pressing
    // it would do -- and these double as the summary of the run.
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
    // The number the patch will actually contain, said before the dialog rather
    // than discovered from a shorter file than expected.
    show([...ROWS, finding({ id: "prose", replacement: null })]);
    // By name, not by position: rows are sorted worst-first, so the row with no
    // code is not the last one just because it was appended last.
    await userEvent.click(screen.getByRole("checkbox", { name: /문제 prose/ }));
    expect(screen.getByText(/패치 없는 것/)).toBeInTheDocument();
  });
});
