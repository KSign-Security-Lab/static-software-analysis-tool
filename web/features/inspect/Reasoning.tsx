"use client";

import { Route, Workflow } from "lucide-react";
import { useState } from "react";

import { Disclosure } from "@/components/panel/disclosure";
import Call from "@/features/inspect/Call";
import Structure from "@/features/inspect/Structure";
import { Meta } from "@/components/panel/code-block";
import type { UiFinding } from "@/lib/model/finding";
import { useClaimTrail } from "@/lib/run/claim-trail";
import { idOf, useSelection } from "@/lib/run/selection";
import { outcomeOf } from "@/lib/trace/outcome";
import { labelOf, seconds } from "@/lib/trace/process";
import { cn } from "@/lib/utils";

/**
 * How this claim was reached, when somebody asks.
 *
 * Both halves were full-width centre tabs and neither was read, because looking
 * at a finding's reasoning meant navigating away from the finding. They are
 * sections of it now, and closed: the question they answer is a second question,
 * and a screen that answers it permanently is a screen answering the first one
 * badly.
 *
 * Closed also means unmounted, which matters more than it reads: the trail joins
 * two queries -- the run's spans and its threads -- and the drawing is React Flow
 * plus a dagre layout. Neither should be paid for by a reader who only wanted to
 * know what was wrong.
 */
export default function Reasoning({ finding }: { finding: UiFinding }) {
  const [process, setProcess] = useState(false);
  const [structure, setStructure] = useState(false);

  return (
    <div className="space-y-1 border-t border-line pt-3">
      <Disclosure
        open={process}
        onOpenChange={setProcess}
        tone="group"
        label={
          <span className="flex items-center gap-1.5">
            <Route className="size-3.5 text-ink-faint" aria-hidden />
            판단 과정
          </span>
        }
        className="-mx-2.5"
      >
        {process && <Trail finding={finding} />}
      </Disclosure>

      <Disclosure
        open={structure}
        onOpenChange={setStructure}
        tone="group"
        label={
          <span className="flex items-center gap-1.5">
            <Workflow className="size-3.5 text-ink-faint" aria-hidden />
            에이전트 구조
          </span>
        }
        className="-mx-2.5"
      >
        {structure && <Structure finding={finding} />}
      </Disclosure>
    </div>
  );
}

/**
 * The agents that produced this claim, in the order they ran, and what each said.
 *
 * Numbered rather than bulleted, because the order *is* the argument: 선별 before
 * a specialist, the specialist before the evidence, the evidence before the
 * verdict. Picking a step opens the call it was.
 */
function Trail({ finding }: { finding: UiFinding }) {
  const trail = useClaimTrail(finding);
  const { selection, select } = useSelection();
  const openId = idOf(selection, "call");

  if (trail.length === 0) {
    return (
      <p className="px-2.5 py-2 text-2xs leading-relaxed text-ink-faint">
        이 검사에는 이 판단의 대화가 없습니다. 지난 검사 결과를 그대로 가져왔을 수 있습니다 — 같은 코드를 다시 읽지
        않으므로 호출이 남지 않습니다. 다시 검사하면 이 자리에 쌓입니다.
      </p>
    );
  }

  return (
    <div className="space-y-1 px-2.5 py-1">
      <ol className="space-y-px">
        {trail.map((exchange, index) => {
          const outcome = outcomeOf(exchange);
          const current = exchange.id === openId;
          return (
            <li key={exchange.id}>
              <button
                type="button"
                onClick={() => select(current ? { kind: "finding", id: finding.id } : { kind: "call", id: exchange.id })}
                className={cn(
                  "flex w-full items-start gap-2 rounded border-l-2 px-1.5 py-1 text-left transition-colors",
                  current ? "border-l-accent bg-surface-2" : "border-l-transparent hover:bg-surface-2",
                )}
              >
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

              {/* Opened in place, under the step it belongs to. It used to
                  replace the finding in a 400px column, so inspecting one line
                  of an argument cost you the argument. */}
              {current && <Call exchange={exchange} />}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

/** The same four tones the record uses. `danger` means a claim survived. */
const TONE: Record<string, string> = {
  plain: "text-ink",
  quiet: "text-ink-faint",
  ok: "text-ok",
  danger: "text-danger",
};
