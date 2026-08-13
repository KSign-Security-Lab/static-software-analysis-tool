import type { AgentStep, Thread, ToolCall, Turn } from "@/lib/api/types";

/**
 * The run as a sequence of exchanges, unit by unit.
 *
 * The record used to be presented two ways and neither answered the question
 * people actually had. The call tree was faithful and unreadable: two thirds of
 * its rows were framework plumbing -- `context`, `skip`, four `triage` chains
 * with nothing in them -- and the prompt behind a row was in a different pane,
 * behind a tab, beside a raw JSON dump of LangGraph's internals. The
 * conversation view had the prompts but no idea what a step *was*, and its tool
 * list never rendered at all.
 *
 * An exchange is what one model call actually consisted of: the brief it was
 * given, the shape it was made to answer in, the tools it was allowed to reach
 * for, the ones it did reach for and what they returned, and the answer. That
 * last-but-one is why this needs `steps` as well as the trace -- a tool that was
 * offered and never called leaves no span behind, so no record of the run can
 * reconstruct it.
 */

/** One tool the model asked for, paired with what running it returned. */
export interface ToolRun extends ToolCall {
  args: Record<string, unknown>;
}

/**
 * One pass of a tool loop: what the model said, and what it ran before saying
 * anything else.
 *
 * `gather` calls, runs what it asked for, and calls again with the results in
 * hand. Flattened into one reply and one list of calls that reads as a summary of
 * a conversation rather than as the conversation -- "it said three things and made
 * three calls" instead of "it wanted the definition, read it, then wanted the
 * caller". The order is the thing worth having.
 */
export interface Round {
  said: string | null;
  calls: ToolRun[];
}

export interface Exchange {
  /** The span id of the first attempt: what the replay endpoint takes. */
  id: string;
  step: string;
  /**
   * How many model calls this one step actually took.
   *
   * More than one for two honest reasons, and neither is a step of its own.
   * `gather` is a loop: it calls, runs what it asked for, and calls again with
   * the results, up to its budget. And a structured call retries under a second
   * method when the first returns nothing usable. Presented as one exchange with
   * a count, because a `net.c` that went through 선별 once should not read as
   * having gone through it twice.
   */
  attempts: number;
  node: string | null;
  /** What this call was about: `proc_0`, `CWE-78 slow.c:9`. */
  subject: string;
  system: string;
  user: string;
  reply: string | null;
  /** What it was allowed to call, whether or not it did. */
  offered: AgentStep["tools"];
  /** What it called, in order, with arguments and results. */
  calls: ToolRun[];
  /** The same calls, still paired with what the model said before each of them. */
  rounds: Round[];
  /** The lens that raised this call's claim, as the agent recorded it. */
  raisedBy: string | null;
  /**
   * Which steps fed this one, and which it fed.
   *
   * The conversation has a shape, and it was invisible: 선별 decides which
   * specialists see a unit, a specialist's finding becomes the claim `gather`
   * investigates, and `gather`'s transcript is pasted into `verify`'s prompt.
   * Four calls in a row said nothing about being four steps of one argument.
   */
  from: string[];
  to: string[];
  latency_ms: number | null;
  tokens: number | null;
  /**
   * The error that decided the outcome -- the last attempt's, not the first.
   *
   * A structured call retries under a second method, so the usual shape is a
   * failed attempt followed by a good one. Reporting any error in the group put a
   * red line under answers that had arrived perfectly well.
   */
  error: string | null;
  /** Attempts that failed and were retried past. Worth knowing, not alarming. */
  retried: number;
}

export interface Unit {
  /** The chunk id, which joins to a finding and to the knowledge graph. */
  id: string;
  symbol: string | null;
  file: string | null;
  exchanges: Exchange[];
  tokens: number;
}

/**
 * The subject of a call, out of its span name.
 *
 * Named `gather:CWE-78 slow.c:9` by `call_config`, so the subject is everything
 * after the first colon -- and a `CWE-78 slow.c:9` contains colons of its own,
 * which is why this splits once rather than taking the last field.
 */
export function subjectOf(name: string, step: string): string {
  const marker = `${step}:`;
  if (name.startsWith(marker)) return name.slice(marker.length);
  const colon = name.indexOf(":");
  return colon === -1 ? "" : name.slice(colon + 1);
}

/**
 * A tool result as the tool actually answered it.
 *
 * MCP returns content blocks, so what the trace recorded is
 * `[{"type":"text","text":"...","id":"lc_…"}]` -- and the text inside is usually
 * itself JSON, so the reader was shown two layers of escaping around the answer
 * and a correlation id nobody can use. The agent unwraps this before handing it
 * to the model; the record kept the envelope, so the panel unwraps it too.
 *
 * Unknown shapes are returned untouched: a wrapper this does not recognise is
 * not licence to hide what it contains.
 */
export function unwrapToolOutput(outputs: unknown): unknown {
  if (!Array.isArray(outputs) || outputs.length === 0) return outputs;

  const texts: string[] = [];
  for (const block of outputs) {
    if (block === null || typeof block !== "object") return outputs;
    const text = (block as { type?: unknown; text?: unknown }).text;
    if (typeof text !== "string") return outputs;
    texts.push(text);
  }
  return texts.join("\n");
}

/**
 * Pair what the model asked for with what came back.
 *
 * Two records of one event: the request is on the model's reply and carries the
 * arguments, the result is a child span and carries the output. Matched by
 * position within a name, because that is all there is -- the trace does not
 * record the tool call id -- and a model that calls `search_text` three times
 * gets three distinct results rather than the first one repeated.
 */
export function pairTools(requested: Turn["tool_calls"], ran: ToolCall[]): ToolRun[] {
  const queues = new Map<string, ToolCall[]>();
  for (const run of ran) queues.set(run.name, [...(queues.get(run.name) ?? []), run]);

  const paired: ToolRun[] = requested.map((call) => {
    const name = String(call.name ?? "");
    const queue = queues.get(name);
    const run = queue?.shift();
    return {
      name,
      args: call.args ?? {},
      inputs: run?.inputs ?? call.args ?? null,
      outputs: run ? unwrapToolOutput(run.outputs) : null,
      error: run?.error ?? null,
      latency_ms: run?.latency_ms ?? null,
    };
  });

  // A tool that ran without a matching request still happened. Kept rather than
  // dropped: the alternative is a panel that silently under-reports what touched
  // the filesystem, which is the opposite of what it is for.
  for (const leftover of queues.values()) {
    for (const run of leftover) {
      paired.push({ ...run, args: asRecord(run.inputs), outputs: unwrapToolOutput(run.outputs) });
    }
  }
  return paired;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function textOf(messages: Turn["messages"], roles: (role: string) => boolean): string {
  return messages
    .filter((message) => roles(message.role))
    .map((message) => message.content)
    .join("\n\n");
}

/**
 * Turn the wire shapes into the panel's model.
 *
 * `node` narrows to one node of the graph -- what clicking a node in 에이전트
 * 구조 means. Compared against the turn's own node rather than matched against
 * its name: a span is named `{step}:{subject}`, so `lens:memory` in the `memory`
 * node is called neither of those things.
 *
 * Linked before it is narrowed, which is the whole subtlety here. `link` reads
 * a conversation to find out which turn fed which -- 선별 naming the specialists
 * it dispatched, a claim passing from a lens to `gather` to `verify` -- and it
 * can only see hand-offs between turns it was given. Narrowing first meant
 * asking a subset of the conversation what it handed to a turn that had already
 * been filtered out, so scoping to a lens dropped that lens's own `→ gather`
 * arrow. Nothing said so: an argument with its edges removed still renders.
 */
export function unitsOf(threads: Thread[], steps: AgentStep[], node?: string | null): Unit[] {
  const byStep = new Map(steps.map((step) => [step.step, step]));

  return threads
    .map((thread) => {
      const whole = link(merge(thread.turns).map((attempts) => exchangeOf(attempts, byStep.get(attempts[0].step))));
      const exchanges = node ? whole.filter((exchange) => exchange.node === node) : whole;
      return {
        id: thread.id,
        symbol: thread.symbol,
        file: thread.file,
        exchanges,
        // Recounted over what is shown, so a narrowed unit does not claim the
        // whole run's spend.
        tokens: exchanges.reduce((sum, exchange) => sum + (exchange.tokens ?? 0), 0),
      };
    })
    .filter((unit) => unit.exchanges.length > 0);
}

/**
 * The subject the run stamped on the calls about one finding.
 *
 * Rebuilt here rather than sent, because it is already sent -- `_finding_subject`
 * on the server names every `gather` and `verify` span `{cwe} {file}:{line}` out
 * of the finding, so the same three fields off a finding reproduce the key that
 * joins it to its own calls. Anchors are resolved in `locate`, which runs before
 * either of them, so the line in the span name is the line in the report.
 */
export function claimOf(finding: { cwe: string | null; primary: { file: string; startLine: number } }): string {
  const where = `${finding.primary.file}:${finding.primary.startLine}`;
  return finding.cwe ? `${finding.cwe} ${where}` : where;
}

/**
 * How one finding was arrived at: its unit, narrowed to the argument that produced it.
 *
 * Narrowing to the unit was already an improvement over showing the whole run, but
 * a unit is not a claim. Five specialists read it and each may raise something, so
 * "이 문제의 대화" was in fact every conversation about the function -- four other
 * arguments about four other lines, and the reader left to work out which of them
 * was the reason for the thing they had open.
 *
 * What belongs here is the chain: the screening that put this unit in front of a
 * specialist, the specialist that raised *this* claim, the evidence gathered for it
 * and the verdict on it. Other lenses and other claims are neither.
 *
 * A subject that matches nothing returns the unit untouched. A trail is a
 * convenience and the transcript is the record: if the join ever fails -- a finding
 * served from the cross-run cache has no calls in *this* run at all -- the reader
 * gets more than they asked for rather than an empty pane implying nothing happened.
 */
export function trailOf(unit: Unit, claim: string): Unit {
  const about = unit.exchanges.filter((each) => each.subject === claim);
  if (about.length === 0) return unit;

  const raised = new Set(about.filter((each) => each.raisedBy).map((each) => `lens:${each.raisedBy}`));
  const exchanges = unit.exchanges.filter(
    (each) =>
      // This claim's own investigation and verdict.
      each.subject === claim ||
      // The specialist that raised it, and not its four colleagues.
      raised.has(each.step) ||
      // Whatever ran before any specialist did -- 선별, and scout when the unit
      // needed narrowing. Stated as "not per-claim and not a lens" so a step
      // added in front of the specialists later is included by default: the risk
      // worth guarding is dropping a step from an explanation, not adding one.
      (each.step !== "gather" && each.step !== "verify" && !each.step.startsWith("lens:")),
  );
  return { ...unit, exchanges, tokens: exchanges.reduce((sum, each) => sum + (each.tokens ?? 0), 0) };
}

/**
 * What a step was doing in that chain, in the reader's language.
 *
 * The step ids are the agent's own and stay the agent's own everywhere they
 * identify something -- a prompt, a breakpoint, a sender. This is the one place
 * they are being *narrated* rather than named, and `lens:injection → gather →
 * verify` is not a sentence about how a vulnerability was found.
 */
export function roleOf(step: string): string {
  if (step === "triage") return "선별";
  if (step === "scout") return "범위 좁히기";
  if (step.startsWith("lens:")) return `${step.slice(5)} 분석`;
  if (step === "gather") return "근거 수집";
  if (step === "verify") return "판정";
  return step;
}

/**
 * What one exchange was doing, which is not always what its step is for.
 *
 * A specialist runs twice over a unit: a lookup pass that may reach for the index
 * -- what is this callee actually declared as -- and then the analysis that answers
 * in the schema. Both are `lens:memory`, so both read as `memory 가 제기`, and the
 * record showed two identical headings where the first had raised nothing and the
 * second was the one that did.
 *
 * Told apart by whether the exchange called a tool, which is structural: the
 * analysis is a guided-decoding call and cannot. The lens's own subject says so too
 * -- the agent suffixes it `조회` -- but a Korean substring is a worse test than the
 * shape of the call.
 */
export function labelOf(exchange: Pick<Exchange, "step" | "calls">): string {
  if (exchange.step.startsWith("lens:") && exchange.calls.length > 0) {
    return `${exchange.step.slice(5)} 조회`;
  }
  return roleOf(exchange.step);
}

/**
 * The attempts of one step, gathered into one entry.
 *
 * Keyed by step *and* subject rather than by adjacency, because a wave verifies
 * several findings at once: the iterations of `gather:CWE-78 net.c:12` and
 * `gather:CWE-122 net.c:12` arrive interleaved, and taking runs of neighbours
 * would split each of them into three.
 *
 * First appearance decides the order, so the sequence still reads as it ran.
 */
function merge(turns: Turn[]): Turn[][] {
  const groups = new Map<string, Turn[]>();
  for (const turn of turns) {
    // `\0` written as an escape rather than as the byte itself. A raw NUL in the
    // source makes the whole file binary to every text tool -- grep skips it in
    // silence, which is a confusing way to be told your search matched nothing.
    const key = `${turn.step}\u0000${subjectOf(turn.name, turn.step)}`;
    groups.set(key, [...(groups.get(key) ?? []), turn]);
  }
  return [...groups.values()];
}

/**
 * Split what a turn asked for into tools and answers.
 *
 * `with_structured_output(..., method="function_calling")` -- the fallback the
 * caller takes when guided decoding returns nothing usable -- delivers the object
 * as a *tool call* named after the schema. It is the answer, and rendering it as
 * a tool made a 선별 that had answered read as "called a tool named triage, then
 *答하지 않았습니다".
 *
 * Told apart by the step's own roster, which is the only sound test available: a
 * step offered no tools cannot have called one, whatever the reply looks like.
 */
function splitCalls(turn: Turn, offered: Set<string>) {
  const asked = turn.tool_calls ?? [];
  const tools = asked.filter((call) => offered.has(String(call.name ?? "")));
  const answers = asked.filter((call) => !offered.has(String(call.name ?? "")));
  return { calls: pairTools(tools, turn.tools ?? []), answers };
}

function exchangeOf(attempts: Turn[], step: AgentStep | undefined): Exchange {
  const first = attempts[0];
  const last = attempts[attempts.length - 1];
  const total = (pick: (turn: Turn) => number | null) =>
    attempts.some((turn) => pick(turn) !== null) ? attempts.reduce((sum, turn) => sum + (pick(turn) ?? 0), 0) : null;

  const offered = new Set((step?.tools ?? []).map((tool) => tool.name));
  const split = attempts.map((turn) => splitCalls(turn, offered));
  const spoken = attempts
    .map((turn) => turn.reply)
    .filter((text): text is string => Boolean(text?.trim()))
    .join("\n\n");
  // The structured object, when it arrived by the function-calling path and there
  // is no prose. Re-serialised so one reader handles both paths.
  const viaToolCall = split.flatMap((each) => each.answers).find((call) => call.args);

  return {
    // The first attempt: its recorded prompt is the brief as it was originally
    // put, which is what a replay should re-ask.
    id: first.id,
    step: first.step,
    attempts: attempts.length,
    node: first.node,
    subject: subjectOf(first.name, first.step),
    system: textOf(first.messages, (role) => role === "system"),
    user: textOf(first.messages, (role) => role !== "system"),
    // Every attempt's, in order: for a tool loop these are the model saying what
    // it still needs to know before it asks for it, which is the reasoning behind
    // the calls below and reads as nonsense with only the last one kept.
    reply: spoken || (viaToolCall ? JSON.stringify(viaToolCall.args) : null),
    offered: step?.tools ?? [],
    calls: split.flatMap((each) => each.calls),
    rounds: attempts.map((turn, index) => ({
      said: turn.reply?.trim() ? turn.reply : null,
      calls: split[index].calls,
    })),
    latency_ms: total((turn) => turn.latency_ms),
    tokens: total((turn) => turn.tokens),
    error: last.error ?? null,
    retried: attempts.slice(0, -1).filter((turn) => turn.error).length,
    // Filled in by `link`, which needs the whole unit to see.
    from: [],
    to: [],
    raisedBy: first.raised_by ?? null,
  };
}

/**
 * Wire one unit's turns to each other.
 *
 * Every edge here is recorded rather than guessed. 선별 names the specialists it
 * dispatches, in its own reply. `gather` and `verify` carry the lens that raised
 * their claim, in the span's metadata. And a `verify` turn is the same argument as
 * the `gather` turn with the same subject -- the subject is `{cwe} {file}:{line}`,
 * derived from the finding, so sharing one means being about one claim.
 */
function link(exchanges: Exchange[]): Exchange[] {
  const triage = exchanges.find((each) => each.step === "triage");
  const dispatched = triage ? dispatchedBy(triage) : [];
  const gathers = exchanges.filter((each) => each.step === "gather");
  const verifies = exchanges.filter((each) => each.step === "verify");

  for (const exchange of exchanges) {
    const from: string[] = [];
    const to: string[] = [];

    if (exchange.step === "triage") {
      to.push(...dispatched);
    } else if (exchange.step.startsWith("lens:")) {
      if (triage && dispatched.includes(exchange.step)) from.push("triage");
      if (gathers.some((each) => each.raisedBy && `lens:${each.raisedBy}` === exchange.step)) to.push("gather");
    } else if (exchange.step === "gather") {
      if (exchange.raisedBy) from.push(`lens:${exchange.raisedBy}`);
      if (verifies.some((each) => each.subject === exchange.subject)) to.push("verify");
    } else if (exchange.step === "verify") {
      if (gathers.some((each) => each.subject === exchange.subject)) from.push("gather");
      if (exchange.raisedBy) from.push(`lens:${exchange.raisedBy}`);
    }

    exchange.from = from;
    exchange.to = to;
  }
  return exchanges;
}

/** The specialists 선별 sent this unit to, out of its own reply. */
function dispatchedBy(triage: Exchange): string[] {
  if (!triage.reply?.trim().startsWith("{")) return [];
  try {
    const parsed: unknown = JSON.parse(triage.reply);
    const lenses = (parsed as { lenses?: unknown })?.lenses;
    if (!Array.isArray(lenses)) return [];
    return lenses.filter((each): each is string => typeof each === "string").map((each) => `lens:${each}`);
  } catch {
    return [];
  }
}

/** `1.42s` / `840ms`, or nothing for a call still running. */
export function seconds(ms: number | null): string {
  if (ms === null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`;
}
