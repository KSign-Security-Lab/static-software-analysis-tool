"use client";

import { AlertTriangle, History, Loader2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { RunStats } from "@/lib/api/types";
import { useStartRun } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * How much of this report this scan actually produced.
 *
 * Two facts, both already in `stats` and neither on screen, and both answering
 * the same question: is the list below what the code contains, or what this run
 * happened to look at?
 *
 * `failed` counts model calls that produced nothing usable, and the commonest
 * cause is the one the log shouts about -- a model too small for the schema emits
 * a valid JSON prefix until it runs out of completion tokens, is retried at
 * double, and runs out again. `nodes.py` is explicit that the unit was then NOT
 * analysed by that lens, and records why it matters: a real buffer overflow was
 * lost exactly this way when `memory` died on the limit while `injection`
 * succeeded, so the unit looked fully read and was not.
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
            아래 목록은 실제로 읽힌 부분의 결과입니다 — 없다는 뜻이 아니라 못 봤다는 뜻입니다. 대개 모델이 스키마를
            끝까지 쓰지 못해서입니다(로그의{" "}
            <code className="font-mono">did not finish a ChunkAnalysis object</code>). 더 큰 모델을 쓰거나{" "}
            <code className="font-mono">AGENT_MAX_TOKENS</code> 를 올리면 줄어듭니다.
          </span>
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
