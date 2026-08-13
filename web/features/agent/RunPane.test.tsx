import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentStep, Thread } from "@/lib/api/types";
import { IDLE } from "@/lib/run/reduce";
import { unitsOf } from "@/lib/trace/process";
import RunPane from "./RunPane";

/**
 * The run read as a conversation.
 *
 * Built from the shapes a live run against `net.c` actually produced: a 선별 that
 * answered in a schema, and a 근거 수집 that reasoned, called two tools and
 * concluded. Asserted by rendering, because the whole claim being made is that it
 * is readable, and no assertion about a data shape can check that.
 */

afterEach(cleanup);

const STEPS: AgentStep[] = [
  {
    step: "triage",
    node: "triage",
    prompt: "triage",
    schema: "Triage",
    schema_fields: ["worth_analysing", "lenses", "reason"],
    tools: [],
    tools_enabled: false,
    max_tool_calls: 0,
    enabled: true,
  },
  {
    step: "gather",
    node: "gather",
    prompt: "gather",
    schema: null,
    schema_fields: [],
    tools: [
      { name: "read_source", summary: "Read a source file from the tree under analysis.", parameters: ["path"] },
      { name: "find_definition", summary: "Where a symbol is defined, with its source text.", parameters: ["symbol"] },
      { name: "run_in_sandbox", summary: "Run a command against the tree, isolated.", parameters: ["command"] },
    ],
    tools_enabled: true,
    max_tool_calls: 4,
    enabled: true,
  },
  {
    step: "lens:logic",
    node: "logic",
    prompt: "lens:logic",
    schema: "ChunkAnalysis",
    schema_fields: ["findings", "note"],
    tools: [],
    tools_enabled: false,
    max_tool_calls: 0,
    enabled: false,
  },
];

const THREADS: Thread[] = [
  {
    id: "d8a2",
    symbol: "ping_host",
    file: "net.c",
    tokens: 6331,
    turns: [
      {
        id: "span-triage",
        step: "triage",
        name: "triage:ping_host",
        node: "triage",
        raised_by: null,
        messages: [
          { role: "system", content: "값싼 첫 통과입니다. 확실하지 않으면 예라고 하십시오." },
          {
            role: "human",
            content:
              "=== UNIT UNDER ANALYSIS: net.c :: ping_host (lines 9-15) ===\n" +
              "009| void ping_host(const char *raw) {\n010|   char cmd[64];\n011|   char *target = pick_target(raw);\n" +
              "012|   sprintf(cmd, \"ping -c 1 %s\", target);\n013|   system(cmd);\n014|   free(target);\n015| }\n" +
              "=== WHAT THIS UNIT'S CALLEES DO ===\n- pick_target: duplicates the input string and returns it.\n" +
              "=== TOP-LEVEL DECLARATIONS IN net.c ===\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n" +
              "=== CALLED FROM ===\n- net.c:17 int main(int argc, char **argv)\n",
          },
        ],
        reply: '{"worth_analysing": true, "lenses": ["memory", "injection"], "reason": "sprintf 와 system 을 씁니다"}',
        tool_calls: [],
        tools: [],
        latency_ms: 1040,
        tokens: 621,
        error: null,
      },
      {
        id: "span-gather",
        step: "gather",
        name: "gather:CWE-122 net.c:12",
        node: "gather",
        raised_by: "injection",
        messages: [
          { role: "system", content: "판정 전에 사실을 확인하십시오." },
          { role: "human", content: "=== CLAIM TO CHECK ===\nUnbounded sprintf at net.c:12" },
        ],
        reply: "argv 에서 그대로 옵니다. 주장은 맞습니다.",
        tool_calls: [
          { name: "find_definition", args: { symbol: "pick_target" } },
          { name: "read_source", args: { path: "net.c", start_line: 15, end_line: 30 } },
        ],
        tools: [
          {
            name: "find_definition",
            inputs: { symbol: "pick_target" },
            outputs: [{ type: "text", text: "[\n  {\n    \"chunk_id\": \"9a4f\",\n    \"file\": \"net.c\",\n    \"symbol\": \"pick_target\",\n    \"kind\": \"function\",\n    \"start_line\": 2,\n    \"end_line\": 6,\n    \"body\": \"static char *pick_target(const char *raw) {\\n    return strdup(raw);\\n}\"\n  }\n]", id: "lc_1" }],
            error: null,
            latency_ms: 432,
          },
          {
            name: "read_source",
            inputs: { path: "net.c" },
            outputs: [{ type: "text", text: "int main(int argc, char **argv)", id: "lc_2" }],
            error: null,
            latency_ms: 420,
          },
        ],
        latency_ms: 5560,
        tokens: 5710,
        error: null,
      },
    ],
  },
];

function setup(over: Partial<Parameters<typeof RunPane>[0]> = {}) {
  const onTunePrompt = vi.fn();
  render(
    <RunPane
      units={unitsOf(THREADS, STEPS)}
      steps={STEPS}
      prompts={[]}
      phase="finished"
      live={IDLE}
      node={null}
      selected={null}
      onTunePrompt={onTunePrompt}
      {...over}
    />,
  );
  return { onTunePrompt };
}

describe("RunPane", () => {
  /** Open a unit's step by the name on its closed row. */
  async function openStep(name: string) {
    await userEvent.click(screen.getByRole("button", { name: new RegExp(name) }));
  }

  it("says what a step decided without being opened", () => {
    // The whole bet of the rewrite: a row is worth not opening. The schema's own
    // keys cannot do that -- `worth_analysing` names a field, not an outcome --
    // so this is the one place the agent's vocabulary becomes the product's.
    setup();
    expect(screen.getByText("분석 대상 · memory, injection")).toBeTruthy();
    // And the detail is not on screen until asked for.
    expect(screen.queryByText("worth_analysing")).toBeNull();
  });

  it("opens a step to the reply in full, under the id the agent files it by", async () => {
    setup();
    await openStep("선별");

    expect(screen.getByText("worth_analysing")).toBeTruthy();
    expect(screen.getByText(/sprintf 와 system 을 씁니다/)).toBeTruthy();
    // `triage` is what the prompt is filed under and what a breakpoint is set on.
    expect(screen.getByText(/^triage/)).toBeTruthy();
  });

  it("keeps the brief a further step in, because it is a template", async () => {
    // The same standing instructions on every unit, wrapped around code that is
    // open two panes to the left.
    setup();
    await openStep("선별");
    expect(screen.queryByText(/=== UNIT UNDER ANALYSIS/)).toBeNull();

    await userEvent.click(screen.getByRole("button", { name: /받은 지시 · [\d,]+ chars/ }));
    expect(screen.getByText(/=== UNIT UNDER ANALYSIS/)).toBeTruthy();
    expect(screen.getByText(/값싼 첫 통과입니다/)).toBeTruthy();
  });

  it("names a step in the reader's language", () => {
    setup();
    expect(screen.getByText("선별")).toBeTruthy();
    expect(screen.getByText("근거 모으기")).toBeTruthy();
  });

  it("says what became of a unit on its own row", () => {
    setup();
    // The last thing that happened to it. Four units used to be four
    // indistinguishable walls of prompt text. Twice on screen here because the
    // unit is open and its last step says the same thing -- which is the point,
    // not a clash: the row is that step's summary standing in for it.
    expect(screen.getAllByText("근거 2건 조회").length).toBeGreaterThan(0);
  });

  it("collapses the units when there is a choice, and opens the one when there is not", () => {
    // One unit is not a menu, so it skips the choosing step.
    setup();
    expect(screen.getByText("선별")).toBeTruthy();

    cleanup();
    setup({ units: unitsOf([THREADS[0], { ...THREADS[0], id: "other", symbol: "send_it" }], STEPS) });
    expect(screen.queryByText("선별")).toBeNull();
    expect(screen.getByText("ping_host")).toBeTruthy();
    expect(screen.getByText("send_it")).toBeTruthy();
    // And a strip over them, so the run has a size before anything is opened.
    expect(screen.getByText(/단위 2 · 호출 4/)).toBeTruthy();
  });

  it("opens everything down to the steps when scoped to one finding", () => {
    // The finding view is this view, filtered -- not a second design.
    setup({ focus: { title: "버퍼 오버플로우", scoped: true, onScoped: vi.fn() } });
    expect(screen.getByText("‘버퍼 오버플로우’ 을 찾아낸 과정")).toBeTruthy();
    expect(screen.getByText("선별")).toBeTruthy();
  });

  it("names a file's own chunk for what it holds", () => {
    // The chunker makes a unit of each file's top-level declarations as well as
    // one of each function, and its symbol *is* the filename -- so it sat in the
    // list looking like a second copy of its own file.
    setup({ units: unitsOf([{ ...THREADS[0], symbol: "net.c", file: "net.c" }], STEPS) });
    expect(screen.getByText("최상위 선언")).toBeTruthy();
    expect(screen.queryByText("net.c")).toBeNull();
  });

  it("puts a file's units under the file", () => {
    // `main.c`, `util.c`, `shorten`, `handle` read as two files and two functions
    // side by side, with nothing saying that handle lives in main.c.
    setup({
      units: unitsOf(
        [
          { ...THREADS[0], id: "whole", symbol: "net.c", file: "net.c" },
          { ...THREADS[0], id: "fn", symbol: "ping_host", file: "net.c" },
        ],
        STEPS,
      ),
    });

    expect(screen.getByText("net.c")).toBeTruthy();
    expect(screen.getByText("단위 2")).toBeTruthy();
    expect(screen.getByText("최상위 선언")).toBeTruthy();
    expect(screen.getByText("ping_host")).toBeTruthy();
  });

  it("does not add a level of hierarchy carrying no information", () => {
    // One unit is not a list: a `net.c` header over a lone `최상위 선언` says
    // nothing the row does not.
    setup({ units: unitsOf([{ ...THREADS[0], symbol: "ping_host", file: "net.c" }], STEPS) });
    expect(screen.queryByText("단위 1")).toBeNull();
    expect(screen.getByText("ping_host")).toBeTruthy();
  });

  it("shows where a step handed on to, and what it spent", async () => {
    setup();
    await openStep("선별");
    expect(screen.getByText("→ lens:memory, lens:injection")).toBeTruthy();
  });

  it("plays a tool loop back as the exchange it was", async () => {
    setup();
    await openStep("근거 모으기");

    expect(screen.getByText(/argv 에서 그대로 옵니다/)).toBeTruthy();
    expect(screen.getByText(/symbol="pick_target"/)).toBeTruthy();
    expect(screen.getByText(/도구 2\/3/)).toBeTruthy();
  });

  it("renders a tool's answer as the facts it is, not as its JSON", async () => {
    // `find_definition` replies with 295 characters of indented JSON headed by a
    // chunk_id, to say a symbol is at a place and here is its body.
    setup({ units: unitsOf([{ ...THREADS[0], turns: [THREADS[0].turns[1]] }], STEPS) });
    await openStep("근거 모으기");

    expect(screen.getByText("pick_target")).toBeTruthy();
    expect(screen.getByText("net.c:2-6")).toBeTruthy();
    expect(screen.queryByText(/chunk_id/)).toBeNull();
  });

  it("keeps the prompt editor out of the way until a turn is hovered", () => {
    setup();
    const edits = screen.getAllByRole("button", { name: "프롬프트 고쳐 다시 실행" });
    expect(edits.length).toBeGreaterThan(1);
    expect(edits[0].className).toContain("opacity-0");
  });

  it("offers the prompt editor from the turn it belongs to", async () => {
    const { onTunePrompt } = setup();
    const [first] = screen.getAllByRole("button", { name: "프롬프트 고쳐 다시 실행" });
    await userEvent.click(first);
    expect(onTunePrompt).toHaveBeenCalledWith("span-triage");
  });

  it("reports what is running by its node name, deduplicated", () => {
    setup({
      phase: "running",
      live: { ...IDLE, running: ["injection", "injection", "verify"], chunk: { id: "c", remaining: 1, total: 4 } },
    });

    expect(screen.getByText("검사 중")).toBeTruthy();
    expect(screen.getByText("injection, verify")).toBeTruthy();
    expect(screen.getByText("3/4")).toBeTruthy();
  });

  it("says when the event stream dropped, rather than looking stuck", () => {
    setup({ phase: "running", live: { ...IDLE, active: true, attached: false } });
    expect(screen.getByText("연결 끊김 · 다시 연결 중")).toBeTruthy();
  });

  it("lists the agents before a run, and not during one", async () => {
    setup({ units: [] });
    await userEvent.click(screen.getByRole("button", { name: /2 agents/ }));
    expect(screen.getByText("lens:logic")).toBeTruthy();

    cleanup();
    setup();
    expect(screen.queryByRole("button", { name: /\d+ agents/ })).toBeNull();
  });
});
