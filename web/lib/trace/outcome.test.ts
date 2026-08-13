import { describe, expect, it } from "vitest";

import { byFile, isWholeFile, outcomeOf, unitOutcome, worst } from "./outcome";
import type { Exchange } from "./process";

function exchange(over: Partial<Exchange> = {}): Exchange {
  return {
    id: "s",
    step: "triage",
    attempts: 1,
    node: "triage",
    subject: "proc_0",
    system: "",
    user: "",
    reply: null,
    offered: [],
    calls: [],
    rounds: [],
    raisedBy: null,
    from: [],
    to: [],
    latency_ms: 10,
    tokens: 10,
    error: null,
    retried: 0,
    ...over,
  };
}

const call = { name: "find_definition", args: {}, inputs: null, outputs: null, error: null, latency_ms: 1 };

describe("outcomeOf", () => {
  it("reads a verdict the way round it actually means", () => {
    // `refuted: true` means there is *no* problem, which is exactly backwards
    // from how the bare field reads at a glance. It is the single easiest mistake
    // to make about this pipeline, so the words carry the tone as well.
    const survived = outcomeOf(exchange({ step: "verify", reply: '{"refuted": false, "confidence": 0.95}' }));
    expect(survived).toEqual({ text: "반박을 견딤 · 95%", tone: "danger" });

    const killed = outcomeOf(exchange({ step: "verify", reply: '{"refuted": true, "confidence": 0.9}' }));
    expect(killed).toEqual({ text: "반박됨 · 90%", tone: "ok" });
  });

  it("says which specialists a screening dispatched", () => {
    const sent = outcomeOf(
      exchange({ reply: '{"worth_analysing": true, "lenses": ["memory", "injection"], "reason": "x"}' }),
    );
    expect(sent?.text).toBe("분석 대상 · memory, injection");

    expect(outcomeOf(exchange({ reply: '{"worth_analysing": false, "reason": "선언뿐"}' }))?.text).toBe("분석 안 함");
  });

  it("counts what a specialist raised", () => {
    expect(outcomeOf(exchange({ step: "lens:memory", reply: '{"findings": [{}, {}]}' }))?.text).toBe("2건 제기");
    expect(outcomeOf(exchange({ step: "lens:memory", reply: '{"findings": []}' }))?.text).toBe("제기 없음");
  });

  it("tells a specialist's lookup pass by the calls it made", () => {
    // It answers in prose rather than a schema, so what it did is what it ran.
    expect(outcomeOf(exchange({ step: "lens:memory", calls: [call, call] }))?.text).toBe("도구 2개");
  });

  it("says how hard a gather looked, having no schema to read", () => {
    expect(outcomeOf(exchange({ step: "gather", calls: [call] }))?.text).toBe("근거 1건 조회");
    expect(outcomeOf(exchange({ step: "gather" }))?.text).toBe("조회 없이 판단");
  });

  it("says nothing rather than something wrong", () => {
    // A reply that will not parse, a field that is missing, a schema that has
    // changed shape. A wrong summary is worse than none: the row falls back to
    // its own name.
    expect(outcomeOf(exchange({ reply: "not json" }))).toBeNull();
    expect(outcomeOf(exchange({ reply: '{"reason": "no verdict field"}' }))).toBeNull();
    expect(outcomeOf(exchange({ step: "verify", reply: '{"refuted": "yes"}' }))).toBeNull();
    expect(outcomeOf(exchange({ step: "locate" }))).toBeNull();
  });

  it("omits a confidence the model did not give", () => {
    expect(outcomeOf(exchange({ step: "verify", reply: '{"refuted": false}' }))?.text).toBe("반박을 견딤");
  });
});

describe("unitOutcome", () => {
  it("is what last happened to the unit", () => {
    const outcome = unitOutcome([
      exchange({ reply: '{"worth_analysing": true, "lenses": ["memory"]}' }),
      exchange({ step: "verify", reply: '{"refuted": false, "confidence": 0.8}' }),
    ]);
    expect(outcome?.text).toBe("반박을 견딤 · 80%");
  });

  it("skips past steps that cannot summarise themselves", () => {
    const outcome = unitOutcome([
      exchange({ reply: '{"worth_analysing": false}' }),
      exchange({ step: "locate" }),
    ]);
    expect(outcome?.text).toBe("분석 안 함");
  });

  it("is nothing when no step could say anything", () => {
    expect(unitOutcome([exchange({ step: "locate" })])).toBeNull();
    expect(unitOutcome([])).toBeNull();
  });
});

describe("byFile", () => {
  it("gathers a file's units under it, in the order they ran", () => {
    const groups = byFile([
      { id: "1", symbol: "main.c", file: "main.c" },
      { id: "2", symbol: "shorten", file: "util.c" },
      { id: "3", symbol: "handle", file: "main.c" },
    ]);

    expect(groups.map((group) => group.file)).toEqual(["main.c", "util.c"]);
    expect(groups[0].units.map((unit) => unit.symbol)).toEqual(["main.c", "handle"]);
  });

  it("still shows a unit the index could not place", () => {
    // Rather than losing it into a group called "null".
    const groups = byFile([{ id: "1", symbol: "orphan", file: null }]);
    expect(groups[0].file).toBe("orphan");
  });
});

describe("isWholeFile", () => {
  it("is the chunk whose symbol is its own filename", () => {
    expect(isWholeFile({ symbol: "main.c", file: "main.c" })).toBe(true);
    expect(isWholeFile({ symbol: "handle", file: "main.c" })).toBe(false);
    expect(isWholeFile({ symbol: null, file: null })).toBe(false);
  });
});

describe("worst", () => {
  it("takes the loudest outcome, not the last", () => {
    // A file whose second function had a claim survive is a file with a problem,
    // whatever its third concluded afterwards.
    const survived = { text: "반박을 견딤", tone: "danger" } as const;
    expect(worst([{ text: "분석 안 함", tone: "quiet" }, survived, { text: "반박됨", tone: "ok" }])).toBe(survived);
  });

  it("is nothing when nothing could say anything", () => {
    expect(worst([null, null])).toBeNull();
  });
});
