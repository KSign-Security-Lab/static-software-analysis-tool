"use client";

import { AlertTriangle } from "lucide-react";

import type { RunStats } from "@/lib/api/types";

/**
 * What the scan did *not* manage to read.
 *
 * `stats.failed` counts model calls that produced nothing usable, and the
 * commonest cause is the one the log shouts about: a model too small for the
 * schema emits a valid JSON prefix until it runs out of completion tokens, gets
 * retried at double, and runs out again. `nodes.py` is explicit that the unit was
 * then NOT analysed by that lens -- and records why it matters, because a real
 * buffer overflow was lost exactly this way when `memory` died on the limit while
 * `injection` succeeded, so the unit looked fully read and was not.
 *
 * Which makes the count the difference between a report and a report you can
 * trust. It was in the payload and on screen nowhere: a scan that failed a third
 * of its calls presented an identical list of findings to one that failed none.
 */
export default function Coverage({ stats }: { stats: RunStats | undefined }) {
  const failed = stats?.failed ?? 0;
  if (failed === 0) return null;

  return (
    <div
      role="alert"
      className="flex shrink-0 flex-wrap items-baseline gap-x-2 gap-y-1 border-b border-warn/40 bg-warn-wash px-2.5 py-1.5"
    >
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0 self-start text-warn" aria-hidden />
      <span className="text-xs text-ink">
        <strong className="font-semibold">{failed.toLocaleString()}번</strong>의 판단이 실패해, 그만큼은 읽히지
        않았습니다
      </span>
      <span className="w-full pl-5 text-2xs leading-relaxed text-ink-faint">
        아래 목록은 실제로 읽힌 부분의 결과입니다 — 없다는 뜻이 아니라 못 봤다는 뜻입니다. 대개 모델이 스키마를 끝까지
        쓰지 못해서입니다(로그의 <code className="font-mono">did not finish a ChunkAnalysis object</code>). 더 큰 모델을
        쓰거나 <code className="font-mono">AGENT_MAX_TOKENS</code> 를 올리면 줄어듭니다.
      </span>
    </div>
  );
}
