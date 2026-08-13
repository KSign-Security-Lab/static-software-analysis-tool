import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AgentStep, Thread } from "@/lib/api/types";
import { IDLE } from "@/lib/run/reduce";
import { unitsOf } from "@/lib/trace/process";
import { TooltipProvider } from "@/components/ui/tooltip";
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
  const props = {
    units: unitsOf(THREADS, STEPS),
    steps: STEPS,
    prompts: [],
    mode: "log" as const,
    onMode: () => {},
    phase: "finished" as const,
    live: IDLE,
    node: null,
    onClearNode: () => {},
    selected: null,
    onTunePrompt,
    ...over,
  };
  // The app mounts one in `app/providers.tsx`; the harness has to as well or
  // the mode switcher throws rather than rendering.
  const view = render(
    <TooltipProvider>
      <RunPane {...props} />
    </TooltipProvider>,
  );
  // Re-rendering rather than re-mounting: mounting fresh per mode is the case
  // that always worked, and the one that did not is a mode changing under a tree
  // that is already on screen.
  const rerender = (mode: Parameters<typeof RunPane>[0]["mode"]) =>
    view.rerender(
      <TooltipProvider>
        <RunPane {...props} mode={mode} />
      </TooltipProvider>,
    );
  return { onTunePrompt, rerender };
}

describe("RunPane", () => {
  const row = (name: string) => screen.getByRole("button", { name: new RegExp(name) });

  it("switches mode on a tree already on screen", async () => {
    // The regression, and the reason for the rewrite. `Collapsible` took
    // `defaultOpen`, which is Radix's *initial* state, and nothing remounted when
    // the mode changed -- so loading `?pane=map` gave a folded tree and switching
    // to 요약 gave the same URL and an unfolded one. Mounting fresh per mode is
    // exactly the case that already worked, so it has to be a click.
    const { rerender } = setup({
      units: unitsOf([THREADS[0], { ...THREADS[0], id: "other", symbol: "send_it" }], STEPS),
    });
    expect(screen.getAllByText("선별").length).toBe(2);

    rerender("map");
    expect(screen.queryByText("선별")).toBeNull();

    rerender("log");
    expect(screen.getAllByText("선별").length).toBe(2);
  });

  it("lets a row be opened by hand, and puts it back when the mode changes", async () => {
    // One gesture overrides one row; changing mode starts again. Without the
    // second half, a tree drifts into a state no control can explain.
    const { rerender } = setup({ mode: "map" });
    expect(screen.queryByText("선별")).toBeNull();

    await userEvent.click(row("ping_host"));
    expect(screen.getByText("선별")).toBeTruthy();

    rerender("log");
    rerender("map");
    expect(screen.queryByText("선별")).toBeNull();
  });

  it("opens to the replies, because 기록 is the record", () => {
    // It used to open to step *rows* and leave every reply, tool call and result
    // behind a click, which is not the full log it is named for.
    setup();

    expect(screen.getByText("worth_analysing")).toBeTruthy();
    expect(screen.getByText(/sprintf 와 system 을 씁니다/)).toBeTruthy();
    // `triage` is what the prompt is filed under and what a breakpoint is set on.
    expect(screen.getByText(/^triage/)).toBeTruthy();
  });

  it("says what a step decided on its closed row", async () => {
    // A row has to be worth not opening. The schema's own keys cannot do that --
    // `worth_analysing` names a field, not an outcome -- so this is the one place
    // the agent's vocabulary becomes the product's.
    setup({ mode: "map" });
    await userEvent.click(row("ping_host"));

    expect(screen.getByText("분석 대상 · memory, injection")).toBeTruthy();
    expect(screen.queryByText("worth_analysing")).toBeNull();
  });

  it("keeps the brief a further step in, because it is a template", async () => {
    // The same standing instructions on every unit, wrapped around code that is
    // open two panes to the left.
    setup();
    expect(screen.queryByText(/=== UNIT UNDER ANALYSIS/)).toBeNull();

    await userEvent.click(screen.getAllByRole("button", { name: /받은 지시 · [\d,]+ chars/ })[0]);
    expect(screen.getByText(/=== UNIT UNDER ANALYSIS/)).toBeTruthy();
    expect(screen.getByText(/값싼 첫 통과입니다/)).toBeTruthy();
  });

  it("names what the pane is narrowed to, and offers a way out", async () => {
    // Clicking a node on the canvas filtered this pane and announced it nowhere.
    const onClearNode = vi.fn();
    setup({ node: "verify", onClearNode });

    expect(screen.getByText("verify 만 보는 중")).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: /verify 만 보는 중 그만두기/ }));
    expect(onClearNode).toHaveBeenCalled();
  });

  it("says nothing about scope when it is showing the whole run", () => {
    setup();
    expect(screen.queryByText(/만 보는 중/)).toBeNull();
  });

  it("names a step in the reader's language", () => {
    setup();
    expect(screen.getByText("선별")).toBeTruthy();
    expect(screen.getByText("근거 수집")).toBeTruthy();
  });

  it("says what became of a unit on its own row", () => {
    setup();
    // The last thing that happened to it. Four units used to be four
    // indistinguishable walls of prompt text. Twice on screen here because the
    // unit is open and its last step says the same thing -- which is the point,
    // not a clash: the row is that step's summary standing in for it.
    expect(screen.getAllByText("근거 2건").length).toBeGreaterThan(0);
  });

  it("opens as the record, because that is the pane's first job", () => {
    // A pane whose job is to be the record should not ask you to guess where to
    // click before it has told you anything. `log` is the default.
    setup({ units: unitsOf([THREADS[0], { ...THREADS[0], id: "other", symbol: "send_it" }], STEPS) });
    expect(screen.getAllByText("선별").length).toBe(2);
  });

  it("folds to one row per unit under 요약", () => {
    setup({
      mode: "map",
      units: unitsOf([THREADS[0], { ...THREADS[0], id: "other", symbol: "send_it" }], STEPS),
    });

    expect(screen.queryByText("선별")).toBeNull();
    expect(screen.getByText("ping_host")).toBeTruthy();
    expect(screen.getByText("send_it")).toBeTruthy();
    // Two facts in the header; the full breakdown is on hover, because all four
    // wanted more width than the header has. `getAll`, because the tooltip
    // renders its copy into the DOM as well.
    expect(screen.getAllByText(/단위 2/).length).toBeGreaterThan(0);
  });

  it("folds a lone unit too, because 요약 means one rule", () => {
    // It used to open itself on the grounds that one unit is not a menu -- true,
    // and a fourth input to "why is this row open" on top of mode, scope and
    // `?span=`. Predictable beats clever here.
    setup({ mode: "map" });
    expect(screen.queryByText("선별")).toBeNull();
    expect(screen.getByText("ping_host")).toBeTruthy();
  });

  it("keeps only the steps that reached for something under 조회", () => {
    // "What did it actually go and read" is a real question, and in the record it
    // is a handful of rows scattered through the whole run.
    setup({ mode: "tools" });

    expect(screen.getByText("근거 수집")).toBeTruthy();
    expect(screen.queryByText("선별")).toBeNull();
    expect(screen.getByText(/symbol="pick_target"/)).toBeTruthy();
  });

  it("says so rather than looking broken when nothing used a tool", () => {
    setup({ mode: "tools", units: unitsOf([{ ...THREADS[0], turns: [THREADS[0].turns[0]] }], STEPS) });
    expect(screen.getByText("이 실행에서 도구를 쓴 단계가 없습니다.")).toBeTruthy();
  });

  it("offers the three readings, and marks the one in use", () => {
    // A shadcn `ToggleGroup` rather than three hand-rolled buttons, so the
    // pressed state is `data-state` and the keyboard behaviour comes with it.
    setup({ mode: "map" });
    expect(screen.getByRole("radio", { name: "요약" }).getAttribute("data-state")).toBe("on");
    expect(screen.getByRole("radio", { name: "기록" }).getAttribute("data-state")).toBe("off");
  });

  it("shows the finding it is narrowed to as a chip beside any other scope", async () => {
    // The finding view is this view, filtered -- not a second design, and not a
    // strip of its own competing with the node's.
    const onScoped = vi.fn();
    setup({ node: "verify", focus: { title: "버퍼 오버플로우", scoped: true, onScoped } });

    expect(screen.getByText("verify 만 보는 중")).toBeTruthy();
    expect(screen.getByText("‘버퍼 오버플로우’ 만 보는 중")).toBeTruthy();

    await userEvent.click(screen.getByRole("button", { name: /버퍼 오버플로우’ 만 보는 중 그만두기/ }));
    expect(onScoped).toHaveBeenCalledWith(false);
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

  it("shows where a step handed on to, and what it spent", () => {
    setup();
    expect(screen.getByText("→ lens:memory, lens:injection")).toBeTruthy();
  });

  it("plays a tool loop back as the exchange it was", () => {
    setup();

    expect(screen.getByText(/argv 에서 그대로 옵니다/)).toBeTruthy();
    expect(screen.getByText(/symbol="pick_target"/)).toBeTruthy();
    expect(screen.getByText(/도구 2\/3/)).toBeTruthy();
  });

  it("renders a tool's answer as the facts it is, not as its JSON", () => {
    // `find_definition` replies with 295 characters of indented JSON headed by a
    // chunk_id, to say a symbol is at a place and here is its body.
    setup({ units: unitsOf([{ ...THREADS[0], turns: [THREADS[0].turns[1]] }], STEPS) });

    expect(screen.getByText("pick_target")).toBeTruthy();
    expect(screen.getByText("net.c:2-6")).toBeTruthy();
    expect(screen.queryByText(/chunk_id/)).toBeNull();
  });

  it("keeps the prompt editor inside the step it acts on", () => {
    // It used to sit on every step row on hover, a second control on the same
    // line as the row's own expand -- appearing under the pointer on the way to
    // the thing you meant to click. It acts on the brief, so it lives beside it.
    setup({ mode: "map" });
    expect(screen.queryByRole("button", { name: /고쳐서 다시 실행/ })).toBeNull();

    cleanup();
    setup();
    expect(screen.getAllByRole("button", { name: /고쳐서 다시 실행/ }).length).toBeGreaterThan(1);
  });

  it("offers the prompt editor from the turn it belongs to", async () => {
    const { onTunePrompt } = setup();
    const [first] = screen.getAllByRole("button", { name: /고쳐서 다시 실행/ });
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
