"use client";

import { useMemo } from "react";

import { AlertTriangle, History, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { RunStats } from "@/lib/api/types";
import { useStartRun } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useSpans } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { failuresByUnit } from "@/lib/trace/failures";

/**
 * How much of this report this scan actually produced.
 *
 * Two facts, both already in `stats` and neither on screen, and both answering
 * the same question: is the list below what the code contains, or what this run
 * happened to look at?
 *
 * `failed` counts model calls that produced nothing usable. The commonest cause
 * is not a model too small for the schema, which is what this used to say: on a
 * reasoning model the reasoning and the JSON come out of one allowance and the
 * reasoning goes first, so the object is cut off having barely started. Run
 * dbd2c9e7ca62 spent 3657 completion tokens to emit 473 characters of JSON.
 * `nodes.py` is explicit that the unit was then NOT analysed by that lens, and
 * records why it matters: a real buffer overflow was lost exactly this way when
 * `memory` died on the limit while `injection` succeeded, so the unit looked
 * fully read and was not.
 *
 * Which is why the count alone was never enough. `failuresByUnit` reads the same
 * spans and says *which* units lost *which* lens -- it was written, tested, and
 * imported by nothing until now.
 *
 * `chunks_cached` counts units served from an earlier run. That is a feature --
 * a chunk id is content-derived and the cache is keyed by the recipe too, so a
 * hit means the same code under the same model and prompts -- but a scan of a
 * re-uploaded tree finishing in five seconds with no model called is startling
 * when nothing says so. It reads as the tool having resumed something.
 */
export default function Coverage({ stats }: { stats: RunStats | undefined }) {
  const [runId] = useRunId();
  const { ensureAttached } = useRunStream();
  const start = useStartRun(runId, ensureAttached);
  // Which units, not just how many calls. `failuresByUnit` has existed and been
  // tested since this banner was written and nothing ever imported it, so a run
  // that left 177 of 673 units partly unread said only `328번의 판단이 실패`.
  const { data: trace } = useSpans(runId);
  const blind = useMemo(() => failuresByUnit(trace?.spans ?? []), [trace]);

  const failed = stats?.failed ?? 0;
  const cached = stats?.chunks_cached ?? 0;
  const inspected = stats?.chunks_inspected ?? 0;
  if (failed === 0 && cached === 0) return null;

  return (
    <div className="shrink-0 divide-y divide-line border-b border-line">
      {failed > 0 && (
        <div role="alert" className="flex flex-wrap items-baseline gap-x-2 gap-y-1 bg-warn-wash px-2.5 py-1.5">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0 self-start text-warn" aria-hidden />
          <span className="text-xs text-ink">
            <strong className="font-semibold">{failed.toLocaleString()}번</strong>의 판단이 실패해, 그만큼은 읽히지
            않았습니다
          </span>
          <span className="w-full pl-5 text-2xs leading-relaxed text-ink-faint">
            아래 목록은 실제로 읽힌 부분의 결과입니다 — 없다는 뜻이 아니라 못 봤다는 뜻입니다. 대개 모델이 답을 끝까지
            쓰지 못해서입니다. <code className="font-mono">AGENT_REASONING_EFFORT</code> 를 낮추거나 더 큰 모델을 쓰면
            줄어듭니다.
          </span>
          {blind.size > 0 && (
            <details className="w-full pl-5">
              <summary className="cursor-pointer text-2xs text-ink-faint hover:text-ink">
                끝까지 읽지 못한 단위 <strong className="font-semibold">{blind.size}개</strong> 보기
              </summary>
              <ul className="mt-1 space-y-0.5">
                {[...blind.entries()].map(([symbol, failures]) => (
                  <li key={symbol} className="text-2xs text-ink-faint">
                    <code className="font-mono text-ink">{symbol}</code>{" "}
                    {[...new Set(failures.map((each) => each.role))].join(", ")} 실패
                  </li>
                ))}
              </ul>
            </details>
          )}
        </div>
      )}

      {cached > 0 && (
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 bg-surface-2 px-2.5 py-1.5">
          <History className="mt-0.5 size-3.5 shrink-0 self-start text-ink-faint" aria-hidden />
          <span className="min-w-0 flex-1 text-xs text-ink">
            {inspected === 0 ? (
              <>
                이번에는 모델을 부르지 않았습니다 — <strong className="font-semibold">{cached}개 단위</strong> 모두 지난
                검사 결과를 그대로 가져왔습니다
              </>
            ) : (
              <>
                <strong className="font-semibold">{cached}개 단위</strong>는 지난 검사 결과를 그대로 가져왔고,{" "}
                {inspected}개만 새로 읽었습니다
              </>
            )}
          </span>
          <Button
            size="sm"
            variant="outline"
            className="shrink-0"
            disabled={start.isPending}
            onClick={() => start.mutate({ force: true })}
          >
            {start.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <RefreshCw className="size-3.5" />}
            전체 다시 검사
          </Button>
          <span className="w-full pl-5 text-2xs leading-relaxed text-ink-faint">
            같은 코드를 같은 모델·프롬프트로 다시 읽어도 답은 같으므로 재사용합니다. 그래서 가져온 단위에는 이 검사의
            ‘판단 과정’ 이 없습니다 — 호출이 일어나지 않았기 때문입니다. 위 버튼은 재사용을 끄고 처음부터 다시 읽습니다.
          </span>
        </div>
      )}
    </div>
  );
}
