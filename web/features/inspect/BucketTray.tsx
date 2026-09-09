"use client";

import { GitPullRequestArrow, X } from "lucide-react";
import { useState } from "react";

import PatchDialog from "@/features/inspect/PatchDialog";
import { Button } from "@/components/ui/button";
import { clear, useBucket } from "@/lib/inspect/bucket";
import { fixableCount } from "@/lib/inspect/filter";
import type { UiFinding } from "@/lib/model/finding";
import { useRunId } from "@/lib/run/use-run-id";

export default function BucketTray({ findings }: { findings: UiFinding[] }) {
  const [runId] = useRunId();
  const ticked = useBucket(runId);
  const [open, setOpen] = useState(false);

  if (ticked.length === 0) return null;

  const fixable = fixableCount(findings, ticked);
  const advice = ticked.length - fixable;

  return (
    <>
      <div className="flex shrink-0 items-center gap-3 border-t border-line bg-surface-2 px-2.5 py-2">
        <span className="min-w-0 text-xs text-ink">
          <strong className="font-semibold text-ink-strong">{ticked.length}건</strong> 담김
          {advice > 0 && (
            <span className="ml-1.5 text-2xs text-warn">
              패치 없는 것 {advice}건
            </span>
          )}
        </span>

        <Button
          size="sm"
          variant="ghost"
          onClick={() => runId && clear(runId)}
          aria-label="담은 것 모두 비우기"
        >
          <X className="size-3.5" />
          비우기
        </Button>

        <Button size="sm" className="ml-auto" onClick={() => setOpen(true)}>
          <GitPullRequestArrow className="size-3.5" />
          패치 만들기
        </Button>
      </div>

      <PatchDialog open={open} onOpenChange={setOpen} findings={findings} />
    </>
  );
}
