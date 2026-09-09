import type { AgentStep, Thread, ToolCall, Turn } from "@/lib/api/types";

export interface ToolRun extends ToolCall {
  args: Record<string, unknown>;
}

export interface Round {
  said: string | null;
  calls: ToolRun[];
}

export interface Exchange {
  id: string;
  step: string;
  attempts: number;
  node: string | null;
  subject: string;
  system: string;
  user: string;
  reply: string | null;
  offered: AgentStep["tools"];
  calls: ToolRun[];
  rounds: Round[];
  raisedBy: string | null;
  from: string[];
  to: string[];
  latency_ms: number | null;
  tokens: number | null;
  error: string | null;
  retried: number;
}

export interface Unit {
  id: string;
  symbol: string | null;
  file: string | null;
  exchanges: Exchange[];
  tokens: number;
}

export function subjectOf(name: string, step: string): string {
  const marker = `${step}:`;
  if (name.startsWith(marker)) return name.slice(marker.length);
  const colon = name.indexOf(":");
  return colon === -1 ? "" : name.slice(colon + 1);
}

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
        tokens: exchanges.reduce((sum, exchange) => sum + (exchange.tokens ?? 0), 0),
      };
    })
    .filter((unit) => unit.exchanges.length > 0);
}

export function claimOf(finding: { cwe: string | null; primary: { file: string; startLine: number } }): string {
  const where = `${finding.primary.file}:${finding.primary.startLine}`;
  return finding.cwe ? `${finding.cwe} ${where}` : where;
}

export function trailOf(unit: Unit, claim: string): Unit {
  const about = unit.exchanges.filter((each) => each.subject === claim);
  if (about.length === 0) return unit;

  const raised = new Set(about.filter((each) => each.raisedBy).map((each) => `lens:${each.raisedBy}`));
  const exchanges = unit.exchanges.filter(
    (each) =>
      each.subject === claim ||
      raised.has(each.step) ||
      (each.step !== "gather" && each.step !== "verify" && !each.step.startsWith("lens:")),
  );
  return { ...unit, exchanges, tokens: exchanges.reduce((sum, each) => sum + (each.tokens ?? 0), 0) };
}

export function roleOf(step: string): string {
  if (step === "triage") return "선별";
  if (step === "scout") return "범위 좁히기";
  if (step.startsWith("lens:")) return `${step.slice(5)} 분석`;
  if (step === "gather") return "근거 수집";
  if (step === "verify") return "판정";
  if (step === "fix") return "고칠 코드 만들기";
  return step;
}

export function labelOf(exchange: Pick<Exchange, "step" | "calls">): string {
  if (exchange.step.startsWith("lens:") && exchange.calls.length > 0) {
    return `${exchange.step.slice(5)} 조회`;
  }
  return roleOf(exchange.step);
}

function merge(turns: Turn[]): Turn[][] {
  const groups = new Map<string, Turn[]>();
  for (const turn of turns) {
    const key = `${turn.step}\u0000${subjectOf(turn.name, turn.step)}`;
    groups.set(key, [...(groups.get(key) ?? []), turn]);
  }
  return [...groups.values()];
}

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
  const viaToolCall = split.flatMap((each) => each.answers).find((call) => call.args);

  return {
    id: first.id,
    step: first.step,
    attempts: attempts.length,
    node: first.node,
    subject: subjectOf(first.name, first.step),
    system: textOf(first.messages, (role) => role === "system"),
    user: textOf(first.messages, (role) => role !== "system"),
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
    from: [],
    to: [],
    raisedBy: first.raised_by ?? null,
  };
}

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

export function seconds(ms: number | null): string {
  if (ms === null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(2)}s`;
}
