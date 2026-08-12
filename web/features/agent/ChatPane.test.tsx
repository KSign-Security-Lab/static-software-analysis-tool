import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentStep, Thread } from "@/lib/api/types";
import { IDLE } from "@/lib/run/reduce";
import { unitsOf } from "@/lib/trace/process";
import ChatPane from "./ChatPane";

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
            outputs: [{ type: "text", text: "static char *pick_target(const char *raw)", id: "lc_1" }],
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

function setup(over: Partial<Parameters<typeof ChatPane>[0]> = {}) {
  const onTunePrompt = vi.fn();
  render(
    <ChatPane
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

describe("ChatPane", () => {
  it("leads a step with what it concluded, not with what it was asked", async () => {
    // The point of the rewrite. A step's brief is a template -- the same standing
    // instructions and the same framing on every unit, around code that is open
    // two panes to the left -- and rendering it first and four times taller than
    // the answer put the emphasis exactly backwards.
    setup();

    expect(screen.getByText("worth_analysing")).toBeTruthy();
    expect(screen.getByText(/sprintf 와 system 을 씁니다/)).toBeTruthy();

    // Folded, and the fold says how much is behind it.
    expect(screen.queryByText(/=== UNIT UNDER ANALYSIS: net\.c :: ping_host/)).toBeNull();
    const brief = screen.getAllByRole("button", { name: /받은 지시 · [\d,]+ chars/ })[0];
    await userEvent.click(brief);
    expect(screen.getByText(/=== UNIT UNDER ANALYSIS: net\.c :: ping_host/)).toBeTruthy();
  });

  it("names a step in the reader's language and keeps the agent's own id beside it", () => {
    // `선별` is what it is doing; `triage` is what the prompt is filed under and
    // what a breakpoint is set on. Both, because both are load-bearing.
    setup();
    expect(screen.getByText("선별")).toBeTruthy();
    expect(screen.getByText("근거 모으기")).toBeTruthy();
    expect(screen.getByText("triage")).toBeTruthy();
  });

  it("says what became of the unit, in its header", () => {
    // So a run can be scanned. Four units were four indistinguishable walls of
    // prompt text, and which was screened out in one call and which went the
    // whole way was something you found out by reading all of both.
    setup();
    expect(screen.getByText("선별 → 근거 모으기")).toBeTruthy();
  });

  it("does not print the unit's name twice when the file is the name", () => {
    // A file chunk's symbol *is* its filename, and `main.c main.c` was the header
    // on every one of them.
    setup({ units: unitsOf([{ ...THREADS[0], symbol: "net.c", file: "net.c" }], STEPS) });
    expect(screen.getAllByText("net.c")).toHaveLength(1);
  });

  it("shows where a step handed on to", () => {
    // triage names the specialists in its own reply.
    setup();
    expect(screen.getByText("→ lens:memory, lens:injection")).toBeTruthy();
  });

  it("plays a tool loop back as the exchange it was", () => {
    // What the model said, then what it asked the tool, then what the tool
    // answered -- in that order. Flattened it read as a tally of three calls.
    setup();

    expect(screen.getByText(/argv 에서 그대로 옵니다/)).toBeTruthy();
    expect(screen.getByText(/symbol="pick_target"/)).toBeTruthy();
    // The answer stays on screen: it is the evidence, not an aside.
    expect(screen.getByText("static char *pick_target(const char *raw)")).toBeTruthy();
  });

  it("clamps a long block rather than hiding it", async () => {
    // Nothing is long enough to clamp until a brief is opened, which is itself the
    // result worth having: a step's own answer fits.
    setup();
    expect(screen.queryAllByRole("button", { name: /더 보기 · [\d,]+ chars/ })).toHaveLength(0);

    await userEvent.click(screen.getAllByRole("button", { name: /받은 지시 · [\d,]+ chars/ })[0]);
    const more = screen.getAllByRole("button", { name: /더 보기 · [\d,]+ chars/ });
    expect(more.length).toBeGreaterThan(0);

    await userEvent.click(more[0]);
    expect(screen.getByRole("button", { name: "접기" })).toBeTruthy();
  });

  it("keeps the standing instructions with the brief rather than in the record", async () => {
    // Identical for every unit this agent reads, and on the node card in full. One
    // disclosure, not a fold nested inside a message.
    setup();
    expect(screen.queryByText(/값싼 첫 통과입니다/)).toBeNull();
    await userEvent.click(screen.getAllByRole("button", { name: /받은 지시 · [\d,]+ chars/ })[0]);
    expect(screen.getByText(/값싼 첫 통과입니다/)).toBeTruthy();
  });

  it("counts the tools a step held against the ones it called", () => {
    // The half no record of the run can supply: a tool offered and never called
    // leaves no span behind. One line of numbers now rather than a disclosure --
    // the roster itself is on the node card.
    setup();
    expect(screen.getByText(/도구 2\/3/)).toBeTruthy();
  });

  it("says nothing about tools for a step that has none", () => {
    setup();
    expect(screen.queryAllByText(/도구 \d+\/\d+/)).toHaveLength(1);
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
