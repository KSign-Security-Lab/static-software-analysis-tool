"use client";

import { ChevronRight } from "lucide-react";

import { Meta } from "@/components/panel/code-block";
import type { UiFinding } from "@/lib/model/finding";
import { useClaimTrail } from "@/lib/run/claim-trail";
import { useSelection } from "@/lib/run/selection";
import { outcomeOf } from "@/lib/trace/outcome";
import { labelOf, seconds } from "@/lib/trace/process";
import { cn } from "@/lib/utils";

/**
 * Which agents produced this finding, and what each of them concluded.
 *
 * The question anyone asks first of a machine-made claim, and the screen could
 * not answer it. The evidence trail above says which *lines* the argument runs
 * through; this says who made it. They are different questions and only one of
 * them was on screen: the other was derivable from a tree of collapsed rows in
 * the 기록 tab, if you knew that `lens:injection → gather → verify` was a chain
 * rather than three unrelated calls.
 *
 * Ordered, numbered and narrated. `labelOf` has existed since the transcript
 * learned to name a step in the reader's language -- 선별, injection 조회,
 * injection 분석, 근거 수집, 판정 -- and until now only ever labelled a row in a
 * list where the order was incidental. Here the order *is* the argument.
 *
 * `labelOf` rather than `roleOf`, because a specialist runs twice over a unit: a
 * lookup pass that reaches for the index, then the analysis that answers in the
 * schema. Both are `lens:injection`, and with the bare role the chain listed
 * `injection 분석` twice with no way to tell which one raised the claim.
 *
 * A row selects that call, so the summary is a way in rather than a substitute:
 * this pane becomes the call's prompts, reply and tool results. The editor does
 * not move -- a call is not about a line.
 */
export default function DecisionChain({ finding }: { finding: UiFinding }) {
  const trail = useClaimTrail(finding);
  const { select } = useSelection();

  if (trail.length === 0) {
    return (
      <section className="space-y-1 border-t border-line px-3 py-2.5">
        <h4 className="text-2xs text-ink-muted">판단 과정</h4>
        {/* Likely rather than exotic: a re-run reuses cached units, and a cached
            unit is not re-read, so it leaves no calls behind in this run even
            though its findings are in the report. */}
        <p className="text-2xs leading-relaxed text-ink-faint">
          이 판단을 낸 대화가 이 실행에는 없습니다. 지난 검사 결과를 그대로 가져왔을 수 있습니다.
        </p>
      </section>
    );
  }

  return (
    <section className="space-y-1 border-t border-line px-3 py-2.5">
      <h4 className="text-2xs text-ink-muted">판단 과정</h4>
      <ol className="-mx-1">
        {trail.map((exchange, index) => {
          const outcome = outcomeOf(exchange);
          return (
            <li key={exchange.id}>
              <button
                type="button"
                // Selects the call, which is all it takes: 상세 shows whatever is
                // selected, so this row replaces itself with that call's prompts
                // and reply. It used to have to change a tab as well.
                onClick={() => select({ kind: "call", id: exchange.id })}
                className="group flex w-full items-baseline gap-2 rounded-sm px-1 py-1 text-left hover:bg-surface-2"
              >
                {/* The order is the argument, so it is numbered rather than
                    bulleted: 선별 before a specialist, the specialist before the
                    evidence, the evidence before the verdict. */}
                <span className="w-3.5 shrink-0 text-right font-mono text-2xs text-ink-faint">{index + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex flex-wrap items-baseline gap-x-1.5">
                    <span className="text-xs text-ink-strong">{labelOf(exchange)}</span>
                    {exchange.error ? (
                      <span className="text-2xs text-danger">실패</span>
                    ) : (
                      outcome && <span className={cn("text-2xs", TONE[outcome.tone])}>{outcome.text}</span>
                    )}
                  </span>
                  <Meta
                    parts={[
                      exchange.calls.length > 0 && `도구 ${exchange.calls.length}`,
                      exchange.tokens ? `${exchange.tokens.toLocaleString()} tok` : null,
                      seconds(exchange.latency_ms),
                    ]}
                  />
                </span>
                <ChevronRight className="mt-0.5 size-3 shrink-0 text-ink-faint opacity-0 group-hover:opacity-100" />
              </button>
            </li>
          );
        })}
      </ol>
      <p className="px-1 text-2xs text-ink-faint">한 줄을 누르면 그 호출의 전문이 이 자리에 열립니다.</p>
    </section>
  );
}

/** The same four tones the transcript uses. `danger` means a claim survived. */
const TONE: Record<string, string> = {
  plain: "text-ink",
  quiet: "text-ink-faint",
  ok: "text-ok",
  danger: "text-danger",
};
