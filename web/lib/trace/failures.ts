import type { TraceSpan } from "@/lib/api/types";
import { roleOf, subjectOf } from "./process";

/**
 * The calls that did not produce anything, and what each one cost.
 *
 * Read off the trace rather than fetched: `on_llm_error` in the recorder writes
 * the exception onto the span, and a span's name carries its subject
 * (`lens:memory:handle`, `fix:CWE-78 main.c:11`), so which unit or which claim
 * lost an answer is already in data the surface holds.
 *
 * This exists because a run reported `검사 완료 · 문제 2` in green while three
 * of its thirty-five model calls had died on the completion-token limit -- and
 * one of them was the memory analysis of a unit with a real buffer overflow in
 * it. A partial result is still useful. A partial result presented as a whole
 * one is not.
 */

export interface Failure {
  /** The step id as the agent spells it: `lens:memory`, `verify`, `fix`. */
  step: string;
  /** What it was working on: a unit's symbol, or a claim's `CWE file:line`. */
  subject: string;
  /** In the reader's language -- `memory 분석`, `판정`, `고칠 코드 만들기`. */
  role: string;
  message: string;
}

/**
 * Every model call that failed *and stayed failed*, in the order they happened.
 *
 * A call that runs out of completion tokens is retried once with double the
 * headroom, and the retry is its own span under the same name -- so the trace
 * of a recovered call is an error followed by a success. Counting the error
 * alone reported `handle` as `문제 2 · memory 분석 실패` in the same row: the
 * lens both found two things and never ran. An attempt that was made good is
 * not a loss, so an error is only kept when nothing later under that name
 * succeeded.
 *
 * Order is the trace's own: spans arrive as they were recorded.
 */
export function failuresOf(spans: TraceSpan[]): Failure[] {
  const failed = (span: TraceSpan) => Boolean(span.error) || span.status === "error";

  return spans
    .filter((span, index) => {
      if (span.kind !== "llm" || !failed(span)) return false;
      // Retried and recovered: a later attempt at the same work came back.
      return !spans.slice(index + 1).some((later) => later.name === span.name && !failed(later));
    })
    .map((span) => {
      // `lens:memory:handle` splits into the step `lens:memory` and the subject
      // `handle`; `verify:CWE-78 main.c:11` into `verify` and the claim.
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

/**
 * Whether a unit lost an analysis.
 *
 * Keyed by symbol, which is what a `lens:` or `triage:` span names and what the
 * 단위 list shows. A lookup pass (`… 조회`) that failed is dropped: it is a
 * retry away from harmless, and the analysis it feeds either ran or is in here
 * on its own account.
 */
export function failuresByUnit(spans: TraceSpan[]): Map<string, Failure[]> {
  const out = new Map<string, Failure[]>();
  for (const failure of failuresOf(spans)) {
    if (!failure.step.startsWith("lens:") && failure.step !== "triage" && failure.step !== "scout") continue;
    // A lookup pass that died is a degradation, not a loss: the analysis beside
    // it still ran, with less context. If that analysis died too it is in here
    // on its own account.
    if (/\s+조회$/.test(failure.subject)) continue;
    const symbol = failure.subject.split(" ")[0];
    if (!symbol) continue;
    out.set(symbol, [...(out.get(symbol) ?? []), failure]);
  }
  return out;
}

/**
 * Whether a claim lost its verification or its patch.
 *
 * Keyed by the subject the agent builds for a claim -- `CWE-78 main.c:11` --
 * which is exactly what `claimOf` reconstructs from a finding, so the two join
 * without either side knowing about the other.
 */
export function failuresByClaim(spans: TraceSpan[]): Map<string, Failure[]> {
  const out = new Map<string, Failure[]>();
  for (const failure of failuresOf(spans)) {
    if (failure.step !== "verify" && failure.step !== "fix" && failure.step !== "gather") continue;
    if (!failure.subject) continue;
    out.set(failure.subject, [...(out.get(failure.subject) ?? []), failure]);
  }
  return out;
}
