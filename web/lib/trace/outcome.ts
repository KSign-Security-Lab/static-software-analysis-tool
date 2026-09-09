import { REFUTED_LABEL, STANDING_LABEL } from "@/lib/model/finding";
import type { Exchange } from "./process";

export interface Outcome {
  text: string;
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
    return exchange.calls.length > 0
      ? { text: `근거 ${exchange.calls.length}건`, tone: "quiet" }
      : { text: "조회 없음", tone: "quiet" };
  }

  if (exchange.step === "verify") {
    if (!reply || typeof reply.refuted !== "boolean") return null;
    const sure = typeof reply.confidence === "number" ? ` · ${Math.round(reply.confidence * 100)}%` : "";
    return reply.refuted
      ? { text: `${REFUTED_LABEL}${sure}`, tone: "quiet" }
      : { text: `${STANDING_LABEL.confirmed}${sure}`, tone: "plain" };
  }

  return null;
}

const TERM: Record<string, string> = {
  worth_analysing: "분석 대상",
  lenses: "살펴볼 관점",
  reason: "이유",
  regions: "살펴본 구간",
  findings: "발견",
  refuted: "반박 시도",
  confidence: "확신도",
  severity: "심각도",
  title: "제목",
  explanation: "설명",
  remediation: "고치는 방법",
  note: "메모",
  notes: "메모",
  summary: "요약",
  detail: "자세히",
};

const BOOLEAN: Record<string, { yes: string; no: string }> = {
  worth_analysing: { yes: "예", no: "아니요" },
  refuted: { yes: REFUTED_LABEL, no: STANDING_LABEL.confirmed },
};

export interface Glossed {
  term: string;
  value: string;
}

export function gloss(key: string, value: string): Glossed {
  const term = TERM[key] ?? key;

  const bool = BOOLEAN[key];
  if (bool && (value === "true" || value === "false")) {
    return { term, value: value === "true" ? bool.yes : bool.no };
  }

  if (key === "confidence") {
    const sure = Number(value);
    if (Number.isFinite(sure) && sure >= 0 && sure <= 1) return { term, value: `${Math.round(sure * 100)}%` };
  }

  return { term, value };
}

export function unitOutcome(exchanges: Exchange[]): Outcome | null {
  for (let at = exchanges.length - 1; at >= 0; at -= 1) {
    const outcome = outcomeOf(exchanges[at]);
    if (outcome) return outcome;
  }
  return null;
}

export interface FileGroup<T> {
  file: string;
  units: T[];
}

export function byFile<T extends { symbol: string | null; file: string | null; id: string }>(
  units: T[],
): FileGroup<T>[] {
  const groups: FileGroup<T>[] = [];
  for (const unit of units) {
    const file = unit.file ?? unit.symbol ?? unit.id;
    const found = groups.find((group) => group.file === file);
    if (found) found.units.push(unit);
    else groups.push({ file, units: [unit] });
  }
  return groups;
}

export function isWholeFile(unit: { symbol: string | null; file: string | null }): boolean {
  return Boolean(unit.symbol) && unit.symbol === unit.file;
}

export function worst(outcomes: (Outcome | null)[]): Outcome | null {
  const rank: Record<Outcome["tone"], number> = { danger: 3, plain: 2, ok: 1, quiet: 0 };
  let best: Outcome | null = null;
  for (const outcome of outcomes) {
    if (outcome && (best === null || rank[outcome.tone] > rank[best.tone])) best = outcome;
  }
  return best;
}
