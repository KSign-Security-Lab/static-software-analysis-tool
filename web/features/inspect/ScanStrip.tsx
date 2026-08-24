"use client";

import { Loader2, Play, Square } from "lucide-react";
import { useState } from "react";

import Activity from "@/features/inspect/Activity";
import { Button } from "@/components/ui/button";
import { Disclosure } from "@/components/panel/disclosure";
import { Progress as Bar } from "@/components/ui/progress";
import { phaseOf, progressOf } from "@/lib/inspect/stage";
import { useCancelRun } from "@/lib/inspect/queries";
import { useResume } from "@/lib/run/trace-queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * The scan, on the page the results are read on.
 *
 * It used to be a screen: a phase, a bar and a growing list, which swapped for a
 * different page the instant the run ended -- taking the reader's scroll and
 * filters with it. One strip above the same list instead, present only while
 * something is running.
 *
 * The agent detail is a disclosure rather than always on, and closed means
 * *unmounted*: `Activity` reads the spans query, and a reader who only wants
 * findings should not pay for it.
 */
export default function ScanStrip() {
  const [runId] = useRunId();
  const { live } = useRunStream();
  const cancel = useCancelRun(runId);
  const resume = useResume(runId, async () => undefined);
  const [open, setOpen] = useState(false);

  const phase = phaseOf(live);
  const { done, total, fraction } = progressOf(live);

  return (
    <div className="shrink-0 border-b border-line bg-surface">
      <div className="flex items-center gap-3 px-2.5 py-1.5">
        <Loader2 className="size-3.5 shrink-0 animate-spin text-accent-ink" aria-hidden />
        <span className="shrink-0 text-xs font-medium text-ink-strong">{phase ?? "검사 중"}</span>

        {/* Indeterminate until the total is known, rather than a bar sitting at
            zero -- which reads as stuck rather than as counting. */}
        {fraction !== null && <Bar value={fraction * 100} className="h-1 max-w-64 flex-1" />}

        <span className="min-w-0 flex-1 truncate font-mono text-2xs text-ink-faint">
          {total > 0 ? `${done.toLocaleString()} / ${total.toLocaleString()} 단위` : "범위를 정하는 중"}
          {live.scanned.size > 0 && ` · 파일 ${live.scanned.size}`}
        </span>

        {live.interrupted ? (
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
