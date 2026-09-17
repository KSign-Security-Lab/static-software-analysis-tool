import type { TraceSpan } from "@/lib/api/types";
import { roleOf, subjectOf } from "./process";

export interface Failure {
  step: string;
  subject: string;
  role: string;
  message: string;
}

export function failuresOf(spans: TraceSpan[]): Failure[] {
  const failed = (span: TraceSpan) => Boolean(span.error) || span.status === "error";

  return spans
    .filter((span, index) => {
      if (span.kind !== "llm" || !failed(span)) return false;
      return !spans.slice(index + 1).some((later) => later.name === span.name && !failed(later));
    })
    .map((span) => {
      const parts = span.name.split(":");
      const step = parts[0] === "lens" ? parts.slice(0, 2).join(":") : parts[0];
      return {
        step,
        subject: subjectOf(span.name, step),
        role: roleOf(step),
        message: span.error ?? "",
      };
    });
}

export function failuresByUnit(spans: TraceSpan[]): Map<string, Failure[]> {
  const out = new Map<string, Failure[]>();
  for (const failure of failuresOf(spans)) {
    if (!failure.step.startsWith("lens:") && failure.step !== "triage" && failure.step !== "scout") continue;
    if (/\s+조회$/.test(failure.subject)) continue;
    const symbol = failure.subject.split(" ")[0];
    if (!symbol) continue;
    out.set(symbol, [...(out.get(symbol) ?? []), failure]);
  }
  return out;
}

export function failuresByClaim(spans: TraceSpan[]): Map<string, Failure[]> {
  const out = new Map<string, Failure[]>();
  for (const failure of failuresOf(spans)) {
    if (failure.step !== "verify" && failure.step !== "fix" && failure.step !== "gather") continue;
    if (!failure.subject) continue;
    out.set(failure.subject, [...(out.get(failure.subject) ?? []), failure]);
  }
  return out;
}
