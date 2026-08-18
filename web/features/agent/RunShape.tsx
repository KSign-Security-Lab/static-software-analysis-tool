"use client";

import { PanelShell } from "@/components/workbench/PanelShell";
import { Coverage, coverageOf, duration, n } from "@/features/agent/RunSummary";
import { useFindings } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * What this run did, when you are not looking at anything in particular.
 *
 * The right column's content with nothing selected. It used to be an empty
 * state -- an icon and `아래 '실행'에서 하나를 고르세요`, pointing at a pane
 * that had already been renamed twice and by the end did not exist. A column
 * whose resting state is an apology is a column that is 25% of the window doing
 * nothing.
 *
 * These numbers were in a popover on a number in the run strip, which is where
 * the funnel had been hiding: 단위 → 걸러냄 → 후보 → 반박됨 → 문제 is the whole
 * argument for trusting the result, and you had to hover to find it. When the
 * strip was dissected this is where it landed, because "how much of this do I
 * believe" is the question this column answers.
 */
export default function RunShape() {
  const [runId] = useRunId();
  const { live } = useRunStream();
  const findings = useFindings(runId);
  const spans = useSpans(runId);

  const stats = findings.data?.stats;
  const { total, cached, inspected, done } = coverageOf(stats, live);
  const cost = spans.data?.summary;
  const count = findings.data?.findings?.length ?? 0;

  if (!runId) {
    return (
      <PanelShell title="이 검사">
        <p className="px-3 py-3 text-2xs leading-relaxed text-ink-faint">
          왼쪽 ‘파일’ 에 코드를 넣고 위 ‘검사 실행’ 을 누르면, 여기에 이 검사가 무엇을 얼마나 읽었는지 나옵니다.
        </p>
      </PanelShell>
    );
  }

  return (
    <PanelShell title="이 검사">
      <div className="space-y-3 px-3 py-2.5">
        {total > 0 && (
          <section className="space-y-1.5">
            <div className="flex items-baseline gap-2">
              <h4 className="text-2xs text-ink-muted">검사 범위</h4>
              <span className="font-mono text-2xs text-ink-faint">
                단위 {n(done)}/{n(total)}
              </span>
            </div>
            <Coverage total={total} inspected={inspected} cached={cached} className="w-full" />
          </section>
        )}

        {/*
          The funnel. Every number here is a count of units in a state, and the
          five of them together are why the last one should be believed: six
          units went in, three were not worth analysing, three raised a claim,
          one of those was refuted, two survived.
        */}
        {stats && (
          <section className="space-y-1 border-t border-line pt-2.5">
            <h4 className="text-2xs text-ink-muted">판단 흐름</h4>
            <dl className="space-y-0.5">
              <Row term="단위" value={stats.chunks_total} />
              <Row term="걸러냄" value={stats.triaged_out} />
              <Row term="후보" value={stats.candidates} />
              {(stats.refuted ?? 0) > 0 && <Row term="반박됨" value={stats.refuted} />}
              {(stats.dropped_unlocatable ?? 0) > 0 && <Row term="위치 못 찾음" value={stats.dropped_unlocatable} />}
              <Row term="문제" value={count} strong />
            </dl>
          </section>
        )}

        {cost && cost.spans > 0 && (
          <section className="space-y-1 border-t border-line pt-2.5">
            <h4 className="text-2xs text-ink-muted">비용</h4>
            <dl className="space-y-0.5">
              <Row term="모델 호출" value={cost.llm_calls} />
              <Row term="도구 호출" value={cost.tool_calls} />
              <Row term="토큰" value={cost.tokens} />
              {cost.total_ms > 0 && <Row term="걸린 시간" text={duration(cost.total_ms)} />}
            </dl>
          </section>
        )}
      </div>
    </PanelShell>
  );
}

function Row({ term, value, text, strong }: { term: string; value?: number; text?: string; strong?: boolean }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-20 shrink-0 text-2xs text-ink-faint">{term}</dt>
      <dd className={strong ? "font-mono text-2xs font-semibold text-ink-strong" : "font-mono text-2xs text-ink-muted"}>
        {text ?? n(value ?? 0)}
      </dd>
    </div>
  );
}
