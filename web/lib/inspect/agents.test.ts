import { describe, expect, it } from "vitest";

import type { TraceSpan } from "@/lib/api/types";
import { IDLE, type RunLive } from "@/lib/run/reduce";
import { activeAgents, filesInFlight, filesScanned, nodeLabel, recentTools } from "./agents";

/**
 * Turning what the stream says into what a reader can watch.
 *
 * A scan is minutes of nothing visible, so the value here is that the names are
 * the *same* names the structure drawing and 판단 과정 use -- a reader who learns
 * one recognises the other. Which is why these are borrowed from `CODE_ROLE` and
 * `roleOf` rather than coined, and why the test pins that rather than the strings.
 */

const live = (over: Partial<RunLive> = {}): RunLive => ({ ...IDLE, ...over });

function span(over: Partial<TraceSpan> & { id: string; seq: number }): TraceSpan {
  return {
    parent_id: null,
    name: "read_source",
    kind: "tool",
    status: "ok",
    error: null,
    started_at: 0,
    latency_ms: 12,
    tokens: null,
    meta: {},
    inputs: null,
    outputs: null,
    ...over,
  };
}

describe("nodeLabel", () => {
  it("names the deterministic nodes from the drawing's own table", () => {
    expect(nodeLabel("plan")).toBe("차례 고르기");
    expect(nodeLabel("context")).toBe("맥락 모으기");
    expect(nodeLabel("locate")).toBe("위치 찾기");
    expect(nodeLabel("reduce")).toBe("결과 쓰기");
  });

  it("narrates the agent steps the way the decision chain does", () => {
    expect(nodeLabel("triage")).toBe("선별");
    expect(nodeLabel("scout")).toBe("범위 좁히기");
    expect(nodeLabel("gather")).toBe("근거 수집");
    expect(nodeLabel("verify")).toBe("판정");
  });

  it("bridges a lens, which is a node here and a step everywhere else", () => {
    // `roleOf` speaks `lens:memory`; the graph calls the same thing `memory`.
    expect(nodeLabel("memory")).toBe("memory 분석");
    expect(nodeLabel("injection")).toBe("injection 분석");
  });

  it("falls back to the machine name rather than inventing one", () => {
    expect(nodeLabel("something_new")).toBe("something_new");
  });
});

describe("activeAgents", () => {
  it("reports every node running, because several genuinely are", () => {
    // A wave screens in parallel and the specialists are dispatched together;
    // one name would have shown whichever event arrived last.
    const agents = activeAgents(live({ running: ["triage", "memory", "injection"] }));
    expect(agents.map((a) => a.label)).toEqual(["선별", "memory 분석", "injection 분석"]);
    expect(agents.map((a) => a.lens)).toEqual([false, true, true]);
    expect(agents.map((a) => a.count)).toEqual([1, 1, 1]);
  });

  it("counts repeats instead of listing them twice", () => {
    // The graph fans out with `Send`, so one node genuinely runs several times
    // at once. Two rows both reading `건너뛰기 skip` look like a rendering fault,
    // and keying a list by a name that repeats *is* one -- React reported
    // duplicate keys for exactly this.
    const agents = activeAgents(live({ running: ["skip", "skip", "gather", "skip"] }));
    expect(agents).toEqual([
      { node: "skip", label: "건너뛰기", lens: false, count: 3 },
      { node: "gather", label: "근거 수집", lens: false, count: 1 },
    ]);
  });

  it("is empty when nothing is running", () => {
    expect(activeAgents(live())).toEqual([]);
  });
});

describe("filesInFlight", () => {
  it("lists each file once, however many of its units are being read", () => {
    // Keyed by unit on purpose: a wave is often two functions of one file, and a
    // set of files could only be added to.
    const at = live({
      inflight: new Map([
        ["c1", "src/app.c"],
        ["c2", "src/app.c"],
        ["c3", "src/net.c"],
      ]),
    });
    expect(filesInFlight(at)).toEqual(["src/app.c", "src/net.c"]);
  });

  it("is empty between waves", () => {
    expect(filesInFlight(live())).toEqual([]);
  });
});

describe("filesScanned", () => {
  it("is newest first, which is what a live list wants", () => {
    const at = live({ scanned: new Set(["a.c", "b.c", "c.c"]) });
    expect(filesScanned(at)).toEqual(["c.c", "b.c", "a.c"]);
  });

  it("is what a tab that joined late has instead of inflight", () => {
    // The stream cannot be replayed, so every `chunk_started` before the tab
    // attached is gone -- but the chunks that have *finished* since are known.
    const at = live({ inflight: new Map(), scanned: new Set(["src/app.c"]) });
    expect(filesInFlight(at)).toEqual([]);
    expect(filesScanned(at)).toEqual(["src/app.c"]);
  });
});

describe("recentTools", () => {
  it("takes tool spans only, newest first", () => {
    const spans = [
      span({ id: "a", seq: 1 }),
      span({ id: "llm", seq: 2, kind: "llm", name: "lens:memory" }),
      span({ id: "b", seq: 3, name: "grep:strcpy" }),
    ];
    const tools = recentTools(spans);
    expect(tools.map((t) => t.id)).toEqual(["b", "a"]);
  });

  it("splits the subject off the span name", () => {
    const [tool] = recentTools([span({ id: "a", seq: 1, name: "read_source:src/app.c" })]);
    expect(tool.name).toBe("read_source");
    expect(tool.subject).toBe("src/app.c");
  });

  it("leaves a bare name alone rather than inventing a subject", () => {
    const [tool] = recentTools([span({ id: "a", seq: 1, name: "list_files" })]);
    expect(tool.name).toBe("list_files");
    expect(tool.subject).toBe("");
  });

  it("carries whether a call is still going or failed", () => {
    const tools = recentTools([
      span({ id: "a", seq: 2, status: "running", latency_ms: null }),
      span({ id: "b", seq: 1, status: "error" }),
    ]);
    expect(tools[0].running).toBe(true);
    expect(tools[1].failed).toBe(true);
  });

  it("caps the list, because a run makes hundreds", () => {
    const many = Array.from({ length: 30 }, (_, i) => span({ id: `s${i}`, seq: i }));
    expect(recentTools(many, 5)).toHaveLength(5);
  });
});
