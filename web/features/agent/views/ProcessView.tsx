"use client";

import { Route } from "lucide-react";
import { useState } from "react";

import { Meta } from "@/components/panel/code-block";
import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import SpanInspector from "@/features/trace/SpanInspector";
import type { UiFinding } from "@/lib/model/finding";
import { useClaimTrail } from "@/lib/run/claim-trail";
import { usePrompts, useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { outcomeOf } from "@/lib/trace/outcome";
import { labelOf, seconds } from "@/lib/trace/process";
import { cn } from "@/lib/utils";

/**
 * How this claim was reached, and what each step actually said.
 *
 * The chain and the calls behind it were in the same 400px column as the
 * finding, and opening a call *replaced* the finding it belonged to -- you lost
 * the argument in order to inspect one line of it, then navigated back. A call
 * is only ever interesting as a step in an argument, so both halves are here
 * together: the steps down the left, the one you picked opened on the right.
 *
 * At width, because that is the measurement that decided this: a call's input
 * runs to 3,628 characters. Eighty lines of scrolling in the old column;
 * thirty-six here.
 *
 * The finding stays selected the whole time, in the right column, so reading
 * the reasoning never costs you the claim.
 */
export default function ProcessView({ finding }: { finding: UiFinding | null }) {
  const [runId] = useRunId();
  const trail = useClaimTrail(finding ?? undefined);
  const spans = useSpans(runId);
  const prompts = usePrompts();
  /**
   * Which step is open, defaulting to the first.
   *
   * `null` means "whatever the chain starts with" rather than "nothing", so a
   * claim that has just been picked opens on step 1 without an effect having to
   * put it there -- a split pane with one half empty is not a state worth
   * rendering, even for a frame.
   *
   * Reset during render on a change of claim, the way the drafts store resets on
   * a change of run: React re-runs this immediately, so the open step can never
   * belong to the previous finding.
   */
  const [picked, setPicked] = useState<string | null>(null);
  const [shownFor, setShownFor] = useState(finding?.id ?? null);
  if (shownFor !== (finding?.id ?? null)) {
    setShownFor(finding?.id ?? null);
    setPicked(null);
  }
  const openId = picked ?? trail[0]?.id ?? null;
  const setOpenId = setPicked;

  if (!finding) {
    return (
      <PanelShell>
        <EmptyState icon={Route} title="문제를 먼저 고르세요">
          왼쪽 ‘문제’ 에서 하나를 고르면, 그 판단을 낸 에이전트들이 순서대로 나오고 각 단계가 실제로 주고받은 말을 그대로
          볼 수 있습니다.
        </EmptyState>
      </PanelShell>
    );
  }

  if (trail.length === 0) {
    return (
      <PanelShell title="판단 과정">
        {/* Likely rather than exotic: a re-run reuses cached units, and a cached
            unit is not re-read, so it leaves no calls behind in this run even
            though its findings are in the report. */}
        <EmptyState icon={Route} title="이 실행에는 이 판단의 대화가 없습니다">
          지난 검사 결과를 그대로 가져왔을 수 있습니다. 다시 검사하면 이 자리에 그 판단을 낸 호출이 쌓입니다.
        </EmptyState>
      </PanelShell>
    );
  }

  const open = spans.data?.spans.find((each) => each.id === openId) ?? null;

  return (
    <div className="grid h-full min-h-0 grid-cols-[minmax(0,17rem)_minmax(0,1fr)]">
      <div className="min-h-0 min-w-0 border-r border-line">
        <PanelShell title="판단 과정" note={<span className="text-2xs">{trail.length}단계</span>}>
          <ol className="py-1">
            {trail.map((exchange, index) => {
              const outcome = outcomeOf(exchange);
              const current = exchange.id === openId;
              return (
                <li key={exchange.id}>
                  <button
                    type="button"
                    onClick={() => setOpenId(exchange.id)}
                    className={cn(
                      "flex w-full items-start gap-2 border-l-2 px-2 py-1.5 text-left transition-colors",
                      current ? "border-l-accent bg-surface-2" : "border-l-transparent hover:bg-surface-2",
                    )}
                  >
                    {/* The order is the argument, so it is numbered rather than
                        bulleted: 선별 before a specialist, the specialist before
                        the evidence, the evidence before the verdict. */}
                    <span className="w-3.5 shrink-0 pt-0.5 text-right font-mono text-2xs text-ink-faint">
                      {index + 1}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="flex flex-wrap items-baseline gap-x-1.5">
                        <span className={cn("text-xs", current ? "text-ink-strong" : "text-ink")}>
                          {labelOf(exchange)}
                        </span>
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
                  </button>
                </li>
              );
            })}
          </ol>
        </PanelShell>
      </div>

      <div className="min-h-0 min-w-0">
        <PanelShell title={<span className="font-mono text-xs">{open?.name ?? "호출"}</span>}>
          <SpanInspector runId={runId} span={open} prompts={prompts.data ?? []} />
        </PanelShell>
      </div>
    </div>
  );
}

/** The same four tones the transcript uses. `danger` means a claim survived. */
const TONE: Record<string, string> = {
  plain: "text-ink",
  quiet: "text-ink-faint",
  ok: "text-ok",
  danger: "text-danger",
};
