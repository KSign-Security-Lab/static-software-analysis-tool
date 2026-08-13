import { REFUTED_LABEL, STANDING_LABEL } from "@/lib/model/finding";
import type { Exchange } from "./process";

/**
 * What a step decided, in one line.
 *
 * The pane shows a run as rows now, and a row has to be worth not opening. The
 * field names alone are not: `worth_analysing`, `refuted`, `confidence` are the
 * schema's own identifiers, correct in the record and useless as a summary --
 * and `refuted: true` is a double negative that means *there is no problem*,
 * which is exactly backwards from how it reads at a glance.
 *
 * So this is the one place the agent's vocabulary is turned into the product's.
 * `반박을 견딤` and `반박됨` are the words the finding list already uses, not new
 * ones invented here; the schema keys are still shown in full when a step is
 * open, because the record is the record.
 *
 * Every rule fails soft. A reply that will not parse, a field that is missing, a
 * schema that has changed shape: all of them return null and the row shows its
 * name alone. A wrong summary is worse than none.
 */
export interface Outcome {
  text: string;
  /** How it should read at a glance. `danger` means a claim survived. */
  tone: "plain" | "quiet" | "ok" | "danger";
}

function parsed(reply: string | null): Record<string, unknown> | null {
  const text = reply?.trim();
  if (!text?.startsWith("{")) return null;
  try {
    const value: unknown = JSON.parse(text);
    return value && typeof value === "object" && !Array.isArray(value)
      ? (value as Record<string, unknown>)
      : null;
  } catch {
    return null;
  }
}

function count(value: unknown): number | null {
  return Array.isArray(value) ? value.length : null;
}

function names(value: unknown): string {
  return Array.isArray(value) ? value.filter((each) => typeof each === "string").join(", ") : "";
}

export function outcomeOf(exchange: Exchange): Outcome | null {
  // A specialist's lookup pass answers in prose, not a schema: what it did is
  // what it looked up.
  if (exchange.step.startsWith("lens:") && exchange.calls.length > 0) {
    return { text: `도구 ${exchange.calls.length}개`, tone: "quiet" };
  }

  const reply = parsed(exchange.reply);

  if (exchange.step === "triage") {
    if (!reply || typeof reply.worth_analysing !== "boolean") return null;
    if (!reply.worth_analysing) return { text: "분석 안 함", tone: "quiet" };
    const lenses = names(reply.lenses);
    return { text: lenses ? `분석 대상 · ${lenses}` : "분석 대상", tone: "plain" };
  }

  if (exchange.step === "scout") {
    const regions = count(reply?.regions);
    return regions === null ? null : { text: `구간 ${regions}개`, tone: "quiet" };
  }

  if (exchange.step.startsWith("lens:")) {
    const findings = count(reply?.findings);
    if (findings === null) return null;
    return findings > 0
      ? { text: `${findings}건 발견`, tone: "plain" }
      : { text: "발견 없음", tone: "quiet" };
  }

  if (exchange.step === "gather") {
    // A tool loop has no schema to read. What it was about is the claim, which
    // the row already carries, so the news is how hard it looked.
    return exchange.calls.length > 0
      ? { text: `근거 ${exchange.calls.length}건`, tone: "quiet" }
      : { text: "조회 없음", tone: "quiet" };
  }

  if (exchange.step === "verify") {
    if (!reply || typeof reply.refuted !== "boolean") return null;
    const sure = typeof reply.confidence === "number" ? ` · ${Math.round(reply.confidence * 100)}%` : "";
    // Refuted means the claim did *not* survive, so it is the quiet outcome and
    // surviving is the loud one. Reading these the wrong way round is the single
    // easiest mistake to make about this pipeline.
    // The vocabulary is `lib/model/finding.ts`'s, not a second copy: the dock and
    // this pane showed the same fact in opposite colours because each had coined
    // its own words for it.
    return reply.refuted
      ? { text: `${REFUTED_LABEL}${sure}`, tone: "quiet" }
      : { text: `${STANDING_LABEL.confirmed}${sure}`, tone: "plain" };
  }

  return null;
}

/** How a unit ended: the last thing that happened to it, for its collapsed row. */
export function unitOutcome(exchanges: Exchange[]): Outcome | null {
  for (let at = exchanges.length - 1; at >= 0; at -= 1) {
    const outcome = outcomeOf(exchanges[at]);
    if (outcome) return outcome;
  }
  return null;
}

/**
 * The units of one file, and how that file came out.
 *
 * A run's units are a file's top-level declarations *and* each function in it,
 * which is why the list read as `main.c`, `util.c`, `shorten`, `handle` -- two
 * files and two functions, side by side, with nothing saying which was which or
 * that `handle` lives in `main.c`. The chunker's two kinds were showing through
 * as one flat list.
 *
 * A file chunk is told from a function chunk by its symbol being the filename,
 * which is what the store writes: `main.c :: main.c`.
 */
export interface FileGroup<T> {
  file: string;
  units: T[];
}

export function byFile<T extends { symbol: string | null; file: string | null; id: string }>(
  units: T[],
): FileGroup<T>[] {
  const groups: FileGroup<T>[] = [];
  for (const unit of units) {
    // Falls back to the unit's own name, so a unit the index could not place
    // still appears rather than vanishing into a group called "null".
    const file = unit.file ?? unit.symbol ?? unit.id;
    const found = groups.find((group) => group.file === file);
    if (found) found.units.push(unit);
    else groups.push({ file, units: [unit] });
  }
  return groups;
}

/** True for the chunk that holds a file's top-level declarations. */
export function isWholeFile(unit: { symbol: string | null; file: string | null }): boolean {
  return Boolean(unit.symbol) && unit.symbol === unit.file;
}

/**
 * How a file came out, over its units.
 *
 * The loudest outcome rather than the last: a file whose second function had a
 * claim survive is a file with a problem in it, whatever its third function
 * concluded afterwards.
 */
export function worst(outcomes: (Outcome | null)[]): Outcome | null {
  const rank: Record<Outcome["tone"], number> = { danger: 3, plain: 2, ok: 1, quiet: 0 };
  let best: Outcome | null = null;
  for (const outcome of outcomes) {
    if (outcome && (best === null || rank[outcome.tone] > rank[best.tone])) best = outcome;
  }
  return best;
}
