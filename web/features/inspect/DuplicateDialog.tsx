"use client";

import { FolderGit2, History, Loader2, Play, RefreshCw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { UploadResult } from "@/lib/api/types";
import { ago } from "@/lib/format";
import { bestMatch, duplicateOf, summarise } from "@/lib/inspect/duplicate";
import { useDeleteRun, useStartRun } from "@/lib/run/queries";
import { useResume } from "@/lib/run/trace-queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * This code has been scanned before. Asked, rather than discovered afterwards.
 *
 * The cross-run cache means an unchanged tree costs nothing to re-scan -- a
 * re-upload reaches `done` in seconds having called no model. That was already
 * true and already reported, but only *after* the reader had uploaded, pressed
 * start and watched it finish. The useful moment is this one, before any work,
 * and the useful question is not "shall I scan" but "what do you want with the
 * run that already did".
 *
 * Which is why the primary action depends on how that run ended -- see
 * `lib/inspect/duplicate` for the state machine. A finished run has results to
 * open; one that stopped part-way has work to carry on, and carrying on is cheap
 * because `plan` skips every unit already marked inspected.
 *
 * Taking the earlier run deletes the upload that just happened. It was never
 * started and holds a byte-identical copy of the same tree, so keeping it would
 * fill 지난 검사 with unstarted duplicates of one thing.
 */
export default function DuplicateDialog({
  upload,
  onDismiss,
}: {
  upload: UploadResult;
  /** Keep the fresh run and carry on with intake. */
  onDismiss: () => void;
}) {
  const [, setRunId] = useRunId();
  const { ensureAttached } = useRunStream();
  const remove = useDeleteRun();
  const [busy, setBusy] = useState(false);

  // Not `matches[0]`: the API answers newest-first, which is honest and general,
  // but the *offer* wants the most useful one -- see `bestMatch`.
  const match = bestMatch(upload.matches)!;
  const others = upload.matches.length - 1;
  const offer = duplicateOf(match);

  // Two runs are in play and each needs its own binding: work on the run that
  // already has the code, and work on the upload that just happened.
  const startMatch = useStartRun(match.run_id, ensureAttached);
  const startFresh = useStartRun(upload.run_id, ensureAttached);
  const resume = useResume(match.run_id, ensureAttached);

  async function take() {
    setBusy(true);
    try {
      if (offer.action === "resume" || offer.action === "start") {
        // No `force`: carrying on is the point, and `plan` skips every unit
        // already marked inspected.
        await startMatch.mutateAsync({});
      } else if (offer.action === "unpark") {
        await resume.mutateAsync({ action: "resume" });
      }
      // `open` and `watch` start nothing -- there is already an answer, or
      // already a run producing one.
      // The duplicate goes either way: it was never started and its tree is the
      // one being opened.
      await remove.mutateAsync(upload.run_id);
      setRunId(match.run_id);
    } finally {
      setBusy(false);
    }
  }

  async function fresh() {
    setBusy(true);
    try {
      // `force`, or this would re-serve the very cache the dialog just
      // described and finish in seconds having called no model.
      await startFresh.mutateAsync({ force: true });
      onDismiss();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open onOpenChange={(next) => !next && onDismiss()}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>이 코드는 전에 검사했습니다</DialogTitle>
          <DialogDescription>
            올린 파일이 지난 검사와 한 바이트도 다르지 않습니다. 다시 검사해도 같은 답이 나옵니다.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 rounded-md border border-line bg-field px-3 py-2.5">
          <p className="flex items-center gap-1.5 text-sm text-ink-strong">
            {match.origin?.kind === "git" ? (
              <FolderGit2 className="size-3.5 shrink-0 text-ink-faint" aria-hidden />
            ) : (
              <History className="size-3.5 shrink-0 text-ink-faint" aria-hidden />
            )}
            {match.origin?.label ?? match.files.join(", ") ?? match.run_id}
          </p>
          <p className="font-mono text-2xs text-ink-faint">
            {ago(match.updated_at)} · {summarise(match)}
          </p>
          <p className="text-2xs leading-relaxed text-ink-muted">{offer.note}</p>
          {others > 0 && (
            <p className="text-2xs text-ink-faint">같은 코드의 지난 검사가 {others}건 더 있습니다.</p>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => void fresh()} disabled={busy}>
            <RefreshCw className="size-4" />
            새로 검사
          </Button>
          <Button onClick={() => void take()} disabled={busy}>
            {busy ? <Loader2 className="size-4 animate-spin" /> : <Play className="size-4" />}
            {offer.label}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
