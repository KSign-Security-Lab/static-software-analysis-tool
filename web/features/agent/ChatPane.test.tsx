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
    node: "verify",
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
        node: "verify",
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
  it("is a thread of messages: sent on one side, said on the other", () => {
    setup();

    // The sent message is on screen, not folded behind a row of metadata. That
    // was the whole failure: the prompt was never visible as a message.
    expect(screen.getByText("orchestrator → triage")).toBeTruthy();
    expect(screen.getByText(/=== UNIT UNDER ANALYSIS: net\.c :: ping_host/)).toBeTruthy();
    // And the reply is a message from a named sender.
    expect(screen.getByText("triage")).toBeTruthy();
    expect(screen.getByText("worth_analysing")).toBeTruthy();
  });

  it("names each speaker by the id the agent uses for itself", () => {
    // `lens:injection` is what the span metadata says, what the prompt is filed
    // under and what a breakpoint is set on.
    setup();
    expect(screen.getByText("orchestrator → gather")).toBeTruthy();
    // As the sender of its own message, and as the addressee each tool answered.
    expect(screen.getAllByText("gather").length).toBe(3);
    // And as the caller on each tool it addressed.
    expect(screen.getAllByText("gather →").length).toBe(2);
  });

  it("shows who handed a turn over, and who it handed on to", () => {
    setup();
    // triage names the specialists in its own reply.
    expect(screen.getByText("→ lens:memory, lens:injection")).toBeTruthy();
    // gather carries the lens that raised the claim, in the span's metadata.
    expect(screen.getByText("← lens:injection")).toBeTruthy();
  });

  it("plays a tool loop back as the exchange it was", async () => {
    // What the model said, then what it asked the tool, then what the tool
    // answered -- in that order. Flattened it read as a tally of three calls.
    setup();

    expect(screen.getByText(/argv 에서 그대로 옵니다/)).toBeTruthy();
    expect(screen.getByText(/symbol="pick_target"/)).toBeTruthy();
    // The tool answering back is its own message, addressed to the caller.
    expect(screen.getByText("find_definition →")).toBeTruthy();
    expect(screen.getByText("static char *pick_target(const char *raw)")).toBeTruthy();
  });

  it("clamps a long message rather than hiding it", async () => {
    setup();
    const more = screen.getAllByRole("button", { name: /더 보기 · [\d,]+ chars/ });
    expect(more.length).toBeGreaterThan(0);
    await userEvent.click(more[0]);
    expect(screen.getByRole("button", { name: "접기" })).toBeTruthy();
  });

  it("keeps the standing instructions out of the thread", async () => {
    // The system prompt is identical for every unit this agent reads. It is an
    // aside, not a message.
    setup();
    expect(screen.queryByText(/값싼 첫 통과입니다/)).toBeNull();
    await userEvent.click(screen.getAllByRole("button", { name: /^system [\d,]+ chars/ })[0]);
    expect(screen.getByText(/값싼 첫 통과입니다/)).toBeTruthy();
  });

  it("counts the tools a step held against the ones it called", async () => {
    // The half no record of the run can supply: a tool offered and never called
    // leaves no span behind.
    setup();
    await userEvent.click(screen.getByRole("button", { name: /tools 3 available, 2 called/ }));
    expect(screen.getByText("run_in_sandbox")).toBeTruthy();
  });

  it("says nothing about tools for a step that has none", () => {
    setup();
    expect(screen.queryAllByRole("button", { name: /tools \d+ available/ })).toHaveLength(1);
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
