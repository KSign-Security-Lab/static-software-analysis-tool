"use client";

import { FileArchive, FileDiff, Loader2, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import { Patch } from "@/components/panel/patch";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import PushForm from "@/features/inspect/PushForm";
import type { PatchPreview, PatchSkip, SkipReason } from "@/lib/api/types";
import { useBucket } from "@/lib/inspect/bucket";
import { useDownloadArchive, usePatchPreview, useSavePatch } from "@/lib/inspect/queries";
import type { UiFinding } from "@/lib/model/finding";
import { useProposeFix, useRun } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";
import { wireId } from "@/lib/model/finding";

/**
 * What the bucket amounts to, before any of it leaves.
 *
 * The preview is asked for first, always, and the refusals are the reason. Three
 * of the four have something the reader can do about them -- write code for an
 * advice-only finding, untick one of two overlapping ones, re-scan a moved
 * anchor -- and a download that quietly contained seven of ten fixes would have
 * told them none of that.
 *
 * The three outputs are deliberately not three dialogs. They are the same
 * selection, and which one somebody wants depends on what they are going to do
 * next: review it, build it, or ship it.
 */
export default function PatchDialog({
  open,
  onOpenChange,
  findings,
}: {
  open: boolean;
  onOpenChange: (next: boolean) => void;
  findings: UiFinding[];
}) {
  const [runId] = useRunId();
  const run = useRun(runId);
  const ticked = useBucket(runId);
  const preview = usePatchPreview(runId);
  const savePatch = useSavePatch(runId);
  const archive = useDownloadArchive(runId);
  const [result, setResult] = useState<PatchPreview | null>(null);

  // Asked once per opening, and again whenever the selection changes underneath
  // -- which it does when a fix is proposed from inside this dialog.
  const key = ticked.join(",");
  useEffect(() => {
    if (!open || !runId || ticked.length === 0) return;
    let live = true;
    void preview.mutateAsync(ticked.map(wireId)).then((next) => {
      if (live) setResult(next);
    });
    return () => {
      live = false;
    };
    // `preview` is a stable mutation object; including it would re-run per render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, runId, key]);

  const origin = run.data?.origin;
  const applied = result?.applied.length ?? 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>패치 만들기</DialogTitle>
          <DialogDescription>
            담은 {ticked.length}건 가운데 실제로 적용되는 것과 그렇지 않은 것을 먼저 보여 드립니다.
          </DialogDescription>
        </DialogHeader>

        {preview.isPending && !result ? (
          <p className="flex items-center gap-2 py-6 text-sm text-ink-muted">
            <Loader2 className="size-4 animate-spin text-ink-faint" aria-hidden />
            패치를 맞춰 보는 중
          </p>
        ) : !result ? (
          <p className="py-6 text-sm text-ink-faint">패치를 만들지 못했습니다.</p>
        ) : (
          <div className="max-h-[60vh] space-y-4 overflow-auto">
            <p className="font-mono text-xs text-ink-muted">
              적용 {applied}건 · 파일 {result.files.length}개
              {result.skipped.length > 0 && ` · 빠짐 ${result.skipped.length}건`}
            </p>

            {result.skipped.length > 0 && (
              <Skipped skipped={result.skipped} findings={findings} />
            )}

            {result.patch ? (
              <Patch diff={result.patch} className="max-h-72" />
            ) : (
              <p className="rounded-md border border-warn/40 bg-warn-wash px-3 py-2 text-xs text-ink">
                적용할 수 있는 것이 없습니다. 위의 이유를 먼저 해결해 주십시오.
              </p>
            )}

            {origin?.kind === "git" && applied > 0 && (
              <PushForm origin={origin} findingIds={ticked.map(wireId)} onDone={() => onOpenChange(false)} />
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            닫기
          </Button>
          <Button
            variant="outline"
            disabled={!result?.patch}
            onClick={() => result?.patch && savePatch(result.patch)}
          >
            <FileDiff className="size-4" />
            패치 파일
          </Button>
          <Button
            disabled={applied === 0 || archive.isPending}
            onClick={() => archive.mutate(ticked.map(wireId))}
          >
            {archive.isPending ? <Loader2 className="size-4 animate-spin" /> : <FileArchive className="size-4" />}
            수정된 소스
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * What did not make it, grouped by why.
 *
 * Grouped rather than listed per finding, because the answer is per reason: one
 * of them is a button, one is "untick something", one is "scan again". A flat
 * list of ten rows each with its own sentence buries that.
 */
function Skipped({ skipped, findings }: { skipped: PatchSkip[]; findings: UiFinding[] }) {
  const [runId] = useRunId();
  const propose = useProposeFix(runId);
  const byReason = new Map<SkipReason, PatchSkip[]>();
  for (const each of skipped) {
    const found = byReason.get(each.reason);
    if (found) found.push(each);
    else byReason.set(each.reason, [each]);
  }

  const titleOf = (id: string) =>
    findings.find((each) => wireId(each.id) === id)?.title ?? id;

  return (
    <div className="space-y-2">
      {[...byReason.entries()].map(([reason, rows]) => (
        <div key={reason} className="rounded-md border border-line bg-field px-3 py-2">
          <p className="text-xs font-medium text-ink-strong">
            {REASON[reason].title}
            <span className="ml-1.5 font-mono text-2xs font-normal text-ink-faint">{rows.length}건</span>
          </p>
          <p className="mt-0.5 text-2xs leading-relaxed text-ink-muted">{REASON[reason].why}</p>
          <ul className="mt-1.5 space-y-1">
            {rows.map((row) => (
              <li key={row.finding_id} className="flex items-baseline gap-2">
                <span className="min-w-0 flex-1 truncate text-2xs text-ink">{titleOf(row.finding_id)}</span>
                {reason === "no_replacement" && (
                  <Button
                    size="sm"
                    variant="ghost"
                    disabled={propose.isPending}
                    onClick={() => propose.mutate(row.finding_id)}
                  >
                    {propose.isPending ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : (
                      <Sparkles className="size-3" />
                    )}
                    고칠 코드 만들기
                  </Button>
                )}
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/** Each refusal, and what the reader can do about it. */
const REASON: Record<SkipReason, { title: string; why: string }> = {
  no_replacement: {
    title: "고칠 코드가 없습니다",
    why: "무엇이 문제인지는 말했지만 그 줄만 바꿔서 고치는 코드는 내놓지 않았습니다. 지금 만들어 달라고 할 수 있습니다.",
  },
  overlap: {
    title: "다른 항목과 줄이 겹칩니다",
    why: "같은 파일의 같은 줄을 두 항목이 고치려 합니다. 더 넓은 범위를 고치는 쪽만 넣었습니다 — 다른 쪽만 넣고 싶으면 이쪽 체크를 빼십시오.",
  },
  stale: {
    title: "검사 이후 코드가 달라졌습니다",
    why: "이 항목이 가리키는 줄이 지금 그 자리에 없습니다. 다시 검사한 뒤에 다시 담아 주십시오.",
  },
  unreadable: {
    title: "이 검사에 없는 파일입니다",
    why: "보고된 파일을 이 검사의 파일 목록에서 찾지 못했습니다. 저희 쪽 문제입니다.",
  },
};
