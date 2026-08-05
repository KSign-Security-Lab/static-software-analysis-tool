"use client";

import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";
import { useRunStream } from "@/lib/run/stream";
import { perspectiveFor } from "@/lib/workbench/perspectives";

/**
 * The 22px strip along the bottom.
 *
 * A flex sibling of the panel group like the activity bar, for the same
 * reason: it is a fixed height, and a percentage panel cannot promise that.
 */

const PHASE_LABEL = {
  idle: null,
  starting: "시작하는 중",
  running: "실행 중",
  paused: "중단점에서 대기",
  finished: "완료",
  failed: "실패",
} as const;

const PHASE_TONE = {
  idle: "",
  starting: "text-ink-muted",
  running: "text-accent-ink",
  paused: "text-warn",
  finished: "text-ok",
  failed: "text-danger",
} as const;

export default function StatusBar() {
  const pathname = usePathname();
  const current = perspectiveFor(pathname);
  const { runId, live, phase } = useRunStream();

  const label = PHASE_LABEL[phase];
  const progress = live.chunk && live.chunk.total > 0 ? `${live.chunk.total - live.chunk.remaining}/${live.chunk.total}` : null;

  return (
    <footer className="flex h-[22px] shrink-0 items-center gap-3 border-t border-line bg-surface px-2.5 text-2xs text-ink-faint">
      <span className="text-ink-muted">{current?.label ?? "SSAT"}</span>
      <span className="truncate">{current?.note}</span>

      {runId && (
        <>
          <span className="text-line-3">|</span>
          <span className="font-mono text-ink-muted">{runId}</span>
        </>
      )}

      {label && (
        <span className={cn("flex items-center gap-1.5", PHASE_TONE[phase])}>
          {phase === "running" && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
          {label}
          {live.running.length > 1 && <span className="text-ink-faint">{live.running.length}개 동시</span>}
        </span>
      )}

      {progress && <span className="font-mono">{progress} 청크</span>}

      {/* A run whose stream dropped keeps its last known phase, which would
          otherwise read as "still running" forever. */}
      {runId && !live.attached && live.active && <span className="text-warn">연결 끊김</span>}

      <span className="ml-auto">로컬 기록 · 외부 전송 없음</span>
    </footer>
  );
}
