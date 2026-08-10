import { describe, expect, it } from "vitest";

import type { AgentStep, Thread, Turn } from "@/lib/api/types";
import { pairTools, subjectOf, unitsOf, unwrapToolOutput } from "./process";

const GATHER: AgentStep = {
  step: "gather",
  node: "verify",
  prompt: "gather",
  schema: null,
  schema_fields: [],
  tools: [
    { name: "read_source", summary: "Read a source file.", parameters: ["path"] },
    { name: "search_text", summary: "Search the tree.", parameters: ["pattern"] },
  ],
  tools_enabled: true,
  max_tool_calls: 4,
  enabled: true,
};

const VERIFY: AgentStep = {
  step: "verify",
  node: "verify",
  prompt: "verify",
  schema: "Verdict",
  schema_fields: ["refuted", "reason", "confidence"],
  tools: [],
  tools_enabled: false,
  max_tool_calls: 0,
  enabled: true,
};

function turn(over: Partial<Turn> = {}): Turn {
  return {
    id: "s1",
    step: "verify",
    name: "verify:CWE-78 slow.c:9",
    node: "verify",
    raised_by: null,
    messages: [
      { role: "system", content: "be hostile" },
      { role: "human", content: "the claim" },
    ],
    reply: '{"refuted": false}',
    tool_calls: [],
    tools: [],
    latency_ms: 1200,
    tokens: 400,
    error: null,
    ...over,
  };
}

function thread(turns: Turn[], over: Partial<Thread> = {}): Thread {
  return { id: "c1", symbol: "proc_0", file: "slow.c", turns, tokens: 0, ...over };
}

describe("subjectOf", () => {
  it("keeps the colons inside a subject", () => {
    // `CWE-78 slow.c:9` has a colon of its own, so taking the last field would
    // leave the reader with "9".
    expect(subjectOf("gather:CWE-78 slow.c:9", "gather")).toBe("CWE-78 slow.c:9");
  });

  it("reads a subject the step prefix does not introduce", () => {
    expect(subjectOf("lens:memory:proc_0", "lens:memory")).toBe("proc_0");
  });

  it("is empty when the name is only the step", () => {
    expect(subjectOf("triage", "triage")).toBe("");
  });
});

describe("unwrapToolOutput", () => {
  it("takes the text out of the MCP content blocks the trace recorded", () => {
    // What a real span holds. The text inside is itself JSON, so leaving the
    // envelope on showed the reader two layers of escaping and an `lc_` id.
    const recorded = [{ type: "text", text: 'net.c:17:int main(int argc, char **argv) {', id: "lc_c12e" }];
    expect(unwrapToolOutput(recorded)).toBe("net.c:17:int main(int argc, char **argv) {");
  });

  it("joins several blocks", () => {
    expect(
      unwrapToolOutput([
        { type: "text", text: "first" },
        { type: "text", text: "second" },
      ]),
    ).toBe("first\nsecond");
  });

  it("leaves a plain string alone", () => {
    expect(unwrapToolOutput("int main(void)")).toBe("int main(void)");
  });

  it("leaves a shape it does not recognise untouched", () => {
    // Not licence to hide what it contains: a wrapper this does not understand
    // is shown as it was recorded.
    const odd = [{ type: "image", data: "…" }];
    expect(unwrapToolOutput(odd)).toBe(odd);
    const truncated = { _truncated: true, _chars: 90_000, preview: "…" };
    expect(unwrapToolOutput(truncated)).toBe(truncated);
  });
});

describe("pairTools", () => {
  it("puts the arguments asked for beside the result that came back", () => {
    const paired = pairTools(
      [{ name: "read_source", args: { path: "slow.c" } }],
      [{ name: "read_source", inputs: { path: "slow.c" }, outputs: "int main(void)", error: null, latency_ms: 40 }],
    );

    expect(paired).toHaveLength(1);
    expect(paired[0]).toMatchObject({ name: "read_source", args: { path: "slow.c" }, outputs: "int main(void)" });
  });

  it("gives repeated calls of one tool their own results", () => {
    const paired = pairTools(
      [
        { name: "search_text", args: { pattern: "strcpy" } },
        { name: "search_text", args: { pattern: "memcpy" } },
      ],
      [
        { name: "search_text", inputs: {}, outputs: "hit one", error: null, latency_ms: 10 },
        { name: "search_text", inputs: {}, outputs: "hit two", error: null, latency_ms: 12 },
      ],
    );

    expect(paired.map((each) => each.outputs)).toEqual(["hit one", "hit two"]);
  });

  it("shows a request whose result was never recorded", () => {
    // A run aborted between the ask and the answer. The ask still happened.
    const [only] = pairTools([{ name: "run_in_sandbox", args: { command: ["gcc"] } }], []);
    expect(only).toMatchObject({ name: "run_in_sandbox", outputs: null, args: { command: ["gcc"] } });
  });

  it("keeps a tool that ran without a matching request", () => {
    const paired = pairTools([], [{ name: "find_callers", inputs: { symbol: "x" }, outputs: "[]", error: null, latency_ms: 5 }]);
    expect(paired).toHaveLength(1);
    expect(paired[0].args).toEqual({ symbol: "x" });
  });
});

describe("unitsOf", () => {
  it("carries the tools a step was offered but did not call", () => {
    // The whole reason the panel reads `steps` as well as the trace: nothing in
    // a record of the run says a tool was available and went unused.
    const [unit] = unitsOf([thread([turn({ step: "gather", name: "gather:CWE-78 slow.c:9", tool_calls: [] })])], [GATHER]);

    expect(unit.exchanges[0].offered.map((tool) => tool.name)).toEqual(["read_source", "search_text"]);
    expect(unit.exchanges[0].calls).toEqual([]);
  });

  it("splits the brief from the message", () => {
    const [unit] = unitsOf([thread([turn()])], [VERIFY]);
    expect(unit.exchanges[0].system).toBe("be hostile");
    expect(unit.exchanges[0].user).toBe("the claim");
  });

  it("drops a unit that made no model calls", () => {
    expect(unitsOf([thread([])], [VERIFY])).toEqual([]);
  });

  it("adds up a unit's tokens across its steps", () => {
    const turns = [turn({ id: "a", tokens: 100 }), turn({ id: "b", name: "verify:other", tokens: 900 })];
    const [unit] = unitsOf([thread(turns)], [VERIFY]);
    expect(unit.tokens).toBe(1000);
  });

  it("narrows to one node by the node, not by the name", () => {
    // What clicking a node in 에이전트 means. `gather` and `verify` are both the
    // `verify` node and neither is called that, so matching the span name would
    // have dropped both.
    const turns = [
      turn({ id: "a", step: "gather", name: "gather:x", node: "verify" }),
      turn({ id: "b", step: "lens:memory", name: "lens:memory:proc_0", node: "memory" }),
    ];
    const [unit] = unitsOf([thread(turns)], [GATHER, VERIFY], "verify");

    expect(unit.exchanges.map((each) => each.id)).toEqual(["a"]);
  });

  it("drops a unit that has nothing left after narrowing", () => {
    expect(unitsOf([thread([turn({ node: "memory" })])], [VERIFY], "verify")).toEqual([]);
  });

  it("counts a narrowed unit's tokens over what is shown", () => {
    const turns = [turn({ id: "a", tokens: 100 }), turn({ id: "b", node: "memory", tokens: 900 })];
    const [unit] = unitsOf([thread(turns)], [VERIFY], "verify");
    expect(unit.tokens).toBe(100);
  });
});

describe("unitsOf, over the attempts one step really takes", () => {
  /**
   * The shape a live run produces. `gather` is a loop -- call, run what it asked
   * for, call again with the results -- and a wave verifies several findings at
   * once, so two findings' iterations arrive interleaved.
   */
  const loop = [
    gatherTurn("g1", "CWE-78 net.c:12", "먼저 정의를 봐야 합니다", "find_definition"),
    gatherTurn("g2", "CWE-122 net.c:12", "호출자를 찾아야 합니다", "search_text"),
    gatherTurn("g3", "CWE-78 net.c:12", "이제 본문을 봅니다", "read_source"),
    gatherTurn("g4", "CWE-78 net.c:12", "argv에서 그대로 옵니다", null),
  ];

  function gatherTurn(id: string, subject: string, reply: string, tool: string | null): Turn {
    return turn({
      id,
      step: "gather",
      name: `gather:${subject}`,
      node: "verify",
      reply,
      tokens: 100,
      latency_ms: 500,
      tool_calls: tool ? [{ name: tool, args: { q: subject } }] : [],
      tools: tool ? [{ name: tool, inputs: { q: subject }, outputs: "found", error: null, latency_ms: 20 }] : [],
    });
  }

  it("folds a tool loop into one step, keyed by subject rather than adjacency", () => {
    const [unit] = unitsOf([thread(loop)], [GATHER]);

    // Two findings, not four steps -- and the interleaving must not split either.
    expect(unit.exchanges.map((each) => each.subject)).toEqual(["CWE-78 net.c:12", "CWE-122 net.c:12"]);
    expect(unit.exchanges[0].attempts).toBe(3);
    expect(unit.exchanges[0].calls.map((each) => each.name)).toEqual(["find_definition", "read_source"]);
  });

  it("keeps every attempt's reply, in order", () => {
    // For a tool loop these are the model saying what it still needs to know
    // before asking for it: the reasoning behind the calls, nonsense truncated.
    const [unit] = unitsOf([thread(loop)], [GATHER]);
    expect(unit.exchanges[0].reply).toBe("먼저 정의를 봐야 합니다\n\n이제 본문을 봅니다\n\nargv에서 그대로 옵니다");
  });

  it("replays the brief as it was first put", () => {
    const [unit] = unitsOf([thread(loop)], [GATHER]);
    expect(unit.exchanges[0].id).toBe("g1");
  });

  it("adds up what the whole step cost", () => {
    const [unit] = unitsOf([thread(loop)], [GATHER]);
    expect(unit.exchanges[0].tokens).toBe(300);
    expect(unit.exchanges[0].latency_ms).toBe(1500);
  });

  it("reads a structured answer that arrived as a tool call as the answer", () => {
    // `with_structured_output(method="function_calling")` delivers the object as
    // a tool call named after the schema. 선별 offers no tools, so this cannot be
    // one -- and rendering it as one made an agent that had answered read as
    // having called a tool and then said nothing.
    const viaTool = turn({
      id: "t1",
      step: "triage",
      name: "triage:net.c",
      node: "triage",
      reply: null,
      tool_calls: [{ name: "triage", args: { worth_analysing: false, reason: "선언만 있습니다" } }],
    });
    const [unit] = unitsOf([thread([viaTool])], []);

    expect(unit.exchanges[0].calls).toEqual([]);
    expect(unit.exchanges[0].reply).toBe('{"worth_analysing":false,"reason":"선언만 있습니다"}');
  });

  it("still treats a call the step really offers as a tool", () => {
    const real = turn({
      id: "g1",
      step: "gather",
      name: "gather:x",
      tool_calls: [{ name: "read_source", args: { path: "net.c" } }],
      tools: [{ name: "read_source", inputs: {}, outputs: "int main(void)", error: null, latency_ms: 9 }],
      reply: null,
    });
    const [unit] = unitsOf([thread([real])], [GATHER]);

    expect(unit.exchanges[0].calls.map((each) => each.name)).toEqual(["read_source"]);
    expect(unit.exchanges[0].reply).toBeNull();
  });

  it("blames the attempt that decided the outcome, not the one that was retried", () => {
    // The usual shape: guided decoding runs out of tokens, the fallback answers.
    // Reporting the first error put a red line under a sound answer.
    const attempts = [
      turn({ id: "a", step: "triage", name: "triage:net.c", error: "length limit", reply: null }),
      turn({ id: "b", step: "triage", name: "triage:net.c", error: null, reply: '{"worth_analysing": true}' }),
    ];
    const [unit] = unitsOf([thread(attempts)], []);

    expect(unit.exchanges[0].error).toBeNull();
    expect(unit.exchanges[0].retried).toBe(1);
  });

  it("keeps an error that was never recovered from", () => {
    const [unit] = unitsOf([thread([turn({ error: "the endpoint went away", reply: null })])], [VERIFY]);
    expect(unit.exchanges[0].error).toBe("the endpoint went away");
    expect(unit.exchanges[0].retried).toBe(0);
  });

  it("folds a structured call retried under another method into one step", () => {
    // `StructuredCaller` falls back from json_schema to function_calling, so one
    // 선별 can be two spans. It went through 선별 once.
    const retried = [
      turn({ id: "t1", step: "triage", name: "triage:net.c", node: "triage", reply: null, tokens: 40 }),
      turn({ id: "t2", step: "triage", name: "triage:net.c", node: "triage", reply: '{"worth_analysing": true}' }),
    ];
    const [unit] = unitsOf([thread(retried)], []);

    expect(unit.exchanges).toHaveLength(1);
    expect(unit.exchanges[0].attempts).toBe(2);
    expect(unit.exchanges[0].reply).toBe('{"worth_analysing": true}');
  });

  it("leaves latency null when nothing has finished", () => {
    const [unit] = unitsOf([thread([turn({ latency_ms: null, tokens: null })])], [VERIFY]);
    expect(unit.exchanges[0].latency_ms).toBeNull();
    expect(unit.exchanges[0].tokens).toBeNull();
  });
});

describe("the hand-offs between agents", () => {
  // Keyed by span id: a unit can hold two `gather` turns, one per claim.
  function unit(turns: Turn[]) {
    const [only] = unitsOf([thread(turns)], [GATHER, VERIFY]);
    return new Map(only.exchanges.map((each) => [each.id, each]));
  }

  it("routes triage to the specialists it named, and only those", () => {
    // Recorded, not guessed: the lenses are in triage's own reply.
    const by = unit([
      turn({
        id: "t",
        step: "triage",
        name: "triage:proc_0",
        node: "triage",
        reply: '{"worth_analysing": true, "lenses": ["memory", "injection"]}',
      }),
      turn({ id: "m", step: "lens:memory", name: "lens:memory:proc_0", node: "memory" }),
      turn({ id: "l", step: "lens:logic", name: "lens:logic:proc_0", node: "logic" }),
    ]);

    expect(by.get("t")!.to).toEqual(["lens:memory", "lens:injection"]);
    expect(by.get("m")!.from).toEqual(["triage"]);
    // Ran without being dispatched -- AGENT_TRIAGE=0 does exactly this -- so
    // claiming triage sent it would be a lie.
    expect(by.get("l")!.from).toEqual([]);
  });

  it("carries a claim from the specialist that raised it through to the verdict", () => {
    const by = unit([
      turn({ id: "i", step: "lens:injection", name: "lens:injection:proc_0", node: "injection" }),
      turn({
        id: "g",
        step: "gather",
        name: "gather:CWE-78 net.c:12",
        node: "verify",
        raised_by: "injection",
      }),
      turn({
        id: "v",
        step: "verify",
        name: "verify:CWE-78 net.c:12",
        node: "verify",
        raised_by: "injection",
      }),
    ]);

    expect(by.get("i")!.to).toEqual(["gather"]);
    expect(by.get("g")!.from).toEqual(["lens:injection"]);
    expect(by.get("g")!.to).toEqual(["verify"]);
    // Both: the transcript came from gather, the claim from the lens.
    expect(by.get("v")!.from).toEqual(["gather", "lens:injection"]);
  });

  it("keeps two claims about one unit apart", () => {
    // A wave verifies several findings at once and their turns interleave; the
    // subject is `{cwe} {file}:{line}`, so sharing one means being one claim.
    const by = unit([
      turn({ id: "g1", step: "gather", name: "gather:CWE-78 net.c:12", node: "verify", raised_by: "injection" }),
      turn({ id: "g2", step: "gather", name: "gather:CWE-122 net.c:12", node: "verify", raised_by: "memory" }),
      turn({ id: "v1", step: "verify", name: "verify:CWE-78 net.c:12", node: "verify", raised_by: "injection" }),
    ]);

    expect(by.get("g1")!.to).toEqual(["verify"]);
    // No verifier ran for this one -- over the per-chunk cap -- and saying it
    // handed off to one would invent a step that never happened.
    expect(by.get("g2")!.to).toEqual([]);
  });

  it("says nothing about a hand-off the agent did not record", () => {
    // Runs traced before the agent carried the lens. Absent, not fabricated.
    const by = unit([turn({ id: "g", step: "gather", name: "gather:CWE-78 net.c:12", node: "verify" })]);
    expect(by.get("g")!.from).toEqual([]);
  });
});
