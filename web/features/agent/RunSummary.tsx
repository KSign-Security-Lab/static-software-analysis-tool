"use client";

import type { RunStats, RunSummary as RunRecord, SpanSummary } from "@/lib/api/types";
import type { RunLive, RunPhase } from "@/lib/run/reduce";
import { cn } from "@/lib/utils";

/**
 * What the run did, in the numbers it already reported.
 *
 * `RunStats` has been arriving with every report and being merged into the
 * cache since the stream was written, and nothing has ever rendered it. Which
 * means the page could say "문제 0건" and had no way to say whether that was
 * because the code is clean, because triage sent every unit away, because
 * verify refuted everything, or because indexing skipped the files and the
 * agent never saw any code at all. Those are four different answers and they
 * looked identical.
 *
 * Coverage is the trust question in a tool like this, so it goes first and it
 * is the one thing drawn rather than only counted.
 */

/**
 * How much of the index this run has got through.
 *
 * Mid-run the report has not been written yet, so the stream's own countdown is
 * the only thing that knows where we are; afterwards the report is authoritative.
 * Exported because the dock's header says the same thing in three words.
 */
export function coverageOf(stats: RunStats | undefined, live: RunLive) {
  const total = stats?.chunks_total ?? live.chunk?.total ?? 0;
  const cached = stats?.chunks_cached ?? 0;
  const inspected = stats?.chunks_inspected ?? (live.chunk ? live.chunk.total - live.chunk.remaining : 0);
  return { total, cached, inspected, done: Math.min(total || inspected, inspected + cached) };
}

/** `3분 12초`, `47초`. */
function duration(ms: number): string {
  const total = Math.round(ms / 1000);
  if (total < 60) return `${total}초`;
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return seconds ? `${minutes}분 ${seconds}초` : `${minutes}분`;
}

const n = (value: number) => value.toLocaleString();

function Row({ term, children }: { term: string; children: React.ReactNode }) {
  return (
    <div className="flex min-w-0 gap-3">
      <dt className="w-14 shrink-0 text-2xs text-ink-faint">{term}</dt>
      <dd className="min-w-0 flex-1 text-2xs text-ink-muted">{children}</dd>
    </div>
  );
}

/** `·`-joined, skipping the parts that had nothing to say. */
function Parts({ of }: { of: (string | null | false)[] }) {
  const kept = of.filter((each): each is string => Boolean(each));
  return (
    <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
      {kept.map((part, index) => (
        <span key={part} className="flex items-center gap-2">
          {index > 0 && <span className="text-line-3">·</span>}
          {part}
        </span>
      ))}
    </span>
  );
}

export default function RunSummary({
  stats,
  spans,
  run,
  live,
  phase,
  findings,
  diff,
}: {
  stats: RunStats | undefined;
  spans: SpanSummary | undefined;
  run: RunRecord | undefined;
  live: RunLive;
  phase: RunPhase;
  findings: number;
  /** Against another run, when one is picked. */
  diff?: { fresh: number; fixed: number; unchanged: number; failed: string | null } | null;
}) {
  const { total, cached, inspected, done } = coverageOf(stats, live);

  const triagedOut = stats?.triaged_out ?? 0;
  const candidates = stats?.candidates ?? 0;
  const refuted = stats?.refuted ?? 0;
  const unlocatable = stats?.dropped_unlocatable ?? 0;

  const indexed = stats?.files_indexed ?? run?.index?.files_indexed ?? 0;
  const skipped = stats?.files_skipped ?? run?.index?.files_skipped ?? 0;

  const nothingYet = total === 0 && indexed === 0 && !spans?.spans;

  if (nothingYet) {
    return (
      <p className="border-b border-line bg-surface-2 px-3 py-2.5 text-2xs text-ink-faint">
        {phase === "idle"
          ? "아직 검사하지 않았습니다. ‘검사 실행’을 누르면 여기에 무엇을 얼마나 살펴봤는지가 쌓입니다."
          : "검사를 시작했습니다. 첫 단위가 끝나는 대로 진행 상황이 여기 나타납니다."}
      </p>
    );
  }

  return (
    <section className="space-y-2 border-b border-line bg-surface-2 px-3 py-2.5">
      <dl className="space-y-1.5">
        <Row term="검사 범위">
          <Parts
            of={[
              indexed > 0 && `파일 ${n(indexed)}개 색인`,
              skipped > 0 && `${n(skipped)}개 건너뜀`,
              total > 0 ? `단위 ${n(total)}개 중 ${n(done)}개 검사` : inspected > 0 ? `단위 ${n(inspected)}개 검사` : null,
              cached > 0 && `캐시 ${n(cached)}`,
            ]}
          />
          {total > 0 && <Coverage total={total} inspected={inspected} cached={cached} />}
        </Row>

        {(triagedOut > 0 || candidates > 0) && (
          <Row term="판단 흐름">
            <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
              <Step label="단위" value={total || inspected} />
              <Arrow />
              <Step label="걸러냄" value={triagedOut} />
              <Arrow />
              <Step label="후보" value={candidates} />
              {refuted > 0 && (
                <>
                  <Arrow />
                  <Step label="반박됨" value={refuted} />
                </>
              )}
              {unlocatable > 0 && (
                <>
                  <Arrow />
                  <Step label="위치 못 찾음" value={unlocatable} />
                </>
              )}
              <Arrow />
              <Step label="문제" value={findings} strong />
            </span>
          </Row>
        )}

        {spans && spans.spans > 0 && (
          <Row term="비용">
            <Parts
              of={[
                spans.llm_calls > 0 && `LLM ${n(spans.llm_calls)}회`,
                spans.tool_calls > 0 && `도구 ${n(spans.tool_calls)}회`,
                spans.tokens > 0 && `${n(spans.tokens)} tok`,
                spans.total_ms > 0 && duration(spans.total_ms),
                spans.errors > 0 && `오류 ${n(spans.errors)}`,
              ]}
            />
          </Row>
        )}
        {diff && (
          <Row term="비교">
            {diff.failed ? (
              <span className="text-danger">{diff.failed}</span>
            ) : (
              <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                <span className="text-accent-ink">새로 {n(diff.fresh)}</span>
                <span className="text-line-3">·</span>
                <span className="text-ok">해결됨 {n(diff.fixed)}</span>
                <span className="text-line-3">·</span>
                <span>그대로 {n(diff.unchanged)}</span>
              </span>
            )}
          </Row>
        )}
      </dl>

      {run?.error && <p className="text-2xs text-danger">{run.error}</p>}
    </section>
  );
}

/**
 * How much of the code was actually read.
 *
 * Three segments over the whole index: read this time, taken from the last run
 * unchanged, and not reached. The last one is the honest part -- an aborted run
 * or one still going leaves a gap, and a bare "8건" would have claimed the
 * whole codebase either way.
 */
function Coverage({ total, inspected, cached }: { total: number; inspected: number; cached: number }) {
  const fresh = Math.max(0, Math.min(inspected, total));
  const reused = Math.max(0, Math.min(cached, total - fresh));

  return (
    <div
      role="meter"
      aria-valuenow={fresh + reused}
      aria-valuemin={0}
      aria-valuemax={total}
      aria-label="검사한 단위"
      className="mt-1 flex h-1 w-full max-w-80 overflow-hidden rounded-full bg-surface-3"
    >
      <div className="bg-accent-solid" style={{ width: `${(fresh / total) * 100}%` }} />
      <div className="bg-accent-wash" style={{ width: `${(reused / total) * 100}%` }} />
    </div>
  );
}

function Step({ label, value, strong }: { label: string; value: number; strong?: boolean }) {
  return (
    <span className="flex items-center gap-1">
      <span className="text-ink-faint">{label}</span>
      <span className={cn("font-mono", strong ? "text-ink-strong" : "text-ink-muted")}>{n(value)}</span>
    </span>
  );
}

const Arrow = () => <span className="text-line-3">→</span>;
