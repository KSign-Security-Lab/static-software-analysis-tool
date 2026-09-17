"use client";

import { CircleStop, Loader2, Play, PlugZap, RotateCcw, Square } from "lucide-react";
import { useState } from "react";

import Activity from "@/features/inspect/Activity";
import { Button } from "@/components/ui/button";
import { Disclosure } from "@/components/panel/disclosure";
import { Progress as Bar } from "@/components/ui/progress";
import { isStopped, phaseOf, progressOf } from "@/lib/inspect/stage";
import { useCancelRun } from "@/lib/inspect/queries";
import { useRun, useStartRun } from "@/lib/run/queries";
import { useResume } from "@/lib/run/trace-queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";

export default function ScanStrip() {
  const [runId] = useRunId();
  const { live, ensureAttached } = useRunStream();
  const run = useRun(runId);
  const cancel = useCancelRun(runId);
  const start = useStartRun(runId, ensureAttached);
  const resume = useResume(runId, ensureAttached);
  const [open, setOpen] = useState(false);

  const phase = phaseOf(live);
  const { done, total, fraction } = progressOf(live);
  const stopped = isStopped({ run: run.data, live });
  const parked = run.data?.status === "interrupted";

  return (
    <div className="shrink-0 border-b border-line bg-surface">
      <div className="flex items-center gap-3 px-2.5 py-1.5">
        {stopped ? (
          <>
            <CircleStop className="size-3.5 shrink-0 text-ink-faint" aria-hidden />
            <span className="shrink-0 text-xs font-medium text-ink-strong">
              {parked ? "중단점에서 멈춰 있습니다" : "중단했습니다"}
            </span>
          </>
        ) : !live.attached ? (
          <>
            <PlugZap className="size-3.5 shrink-0 text-warn" aria-hidden />
            <span className="shrink-0 text-xs font-medium text-ink-strong">
              연결이 끊겼습니다 · 다시 연결하는 중
            </span>
          </>
        ) : (
          <>
            <Loader2 className="size-3.5 shrink-0 animate-spin text-accent-ink" aria-hidden />
            <span className="shrink-0 text-xs font-medium text-ink-strong">{phase ?? "검사 중"}</span>
          </>
        )}

        {!stopped && fraction !== null && <Bar value={fraction * 100} className="h-1 max-w-64 flex-1" />}

        <span className="min-w-0 flex-1 truncate font-mono text-2xs text-ink-faint">
          {total > 0
            ? `${done.toLocaleString()} / ${total.toLocaleString()} 단위`
            : stopped
              ? "찾은 것은 아래에 그대로 남아 있습니다"
              : "범위를 정하는 중"}
          {live.scanned.size > 0 && ` · 파일 ${live.scanned.size}`}
        </span>

        {stopped ? (
          <span className="flex shrink-0 items-center gap-1">
            <Button
              size="sm"
              variant="outline"
              disabled={start.isPending || resume.isPending}
              onClick={() => (parked ? resume.mutate({ action: "resume" }) : start.mutate({}))}
            >
              <Play className="size-3.5" />
              이어서 검사
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={start.isPending || resume.isPending}
              onClick={() => start.mutate({ force: true })}
            >
              <RotateCcw className="size-3.5" />
              전체 다시 검사
            </Button>
          </span>
        ) : live.cancelling ? (
          <Button size="sm" variant="outline" disabled>
            <Loader2 className="size-3.5 animate-spin" />
            중단하는 중
          </Button>
        ) : live.interrupted ? (
          <Button size="sm" variant="outline" onClick={() => resume.mutate({ action: "resume" })}>
            <Play className="size-3.5" />
            이어서
          </Button>
        ) : (
          <Button size="sm" variant="outline" disabled={cancel.isPending} onClick={() => cancel.mutate()}>
            <Square className="size-3.5" />
            중단
          </Button>
        )}
      </div>

      {live.error && <p className="px-2.5 pb-1.5 text-xs text-danger">{live.error}</p>}

      <Disclosure
        open={open}
        onOpenChange={setOpen}
        tone="aside"
        label="지금 무엇을 하고 있는지"
        className="px-2.5 pb-1.5"
      >
        {open && (
          <div className="pt-2">
            <Activity />
          </div>
        )}
      </Disclosure>
    </div>
  );
}
