"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { describeError } from "@/lib/api/client";
import { cancelRun } from "@/lib/api/control";
import { downloadArchive, previewPatch, pushBranch, savePatch } from "@/lib/api/patch";
import { keys } from "@/lib/query/keys";

/**
 * Getting the bucket out of the browser.
 *
 * All mutations, including the preview, and deliberately: the preview is a
 * question about a selection that changes with every tick, so caching it by
 * finding-id-set would be a cache key nobody could invalidate. It is cheap --
 * the server splices in memory and writes nothing.
 *
 * `previewPatch` is asked first in all three flows. What it returns is not just
 * a diff but the refusals, and those are the reason to ask before doing: a
 * bucket of ten where three carry no code produces a patch of seven, and the
 * reader should learn that from a dialog rather than from a short file.
 */

export function usePatchPreview(runId: string | null) {
  return useMutation({
    mutationFn: (findingIds: string[]) => previewPatch(runId!, findingIds),
    onError: (error) => toast.error("패치를 만들 수 없습니다", { description: describeError(error) }),
  });
}

/**
 * Save the diff that is already on screen.
 *
 * Not a mutation over the network at all -- the bytes are in hand from the
 * preview. It lives here so the button beside the other two reads the same way,
 * and so what is saved is provably the diff that was reviewed.
 */
export function useSavePatch(runId: string | null) {
  return (patch: string) => {
    savePatch(runId!, patch);
    toast.success("패치를 내려받았습니다", { description: "git apply 로 적용할 수 있습니다." });
  };
}

export function useDownloadArchive(runId: string | null) {
  return useMutation({
    mutationFn: (findingIds: string[]) => downloadArchive(runId!, findingIds),
    onSuccess: () => toast.success("수정된 소스를 내려받았습니다"),
    onError: (error) => toast.error("소스를 내려받을 수 없습니다", { description: describeError(error) }),
  });
}

/**
 * Commit the fixes on a branch of the run's own remote.
 *
 * Invalidates nothing: the push happens on a clone the server made and threw
 * away, so no run, report or file this page holds has changed. Saying that here
 * is worth more than the line of code it saves -- the reflex is to invalidate
 * after a mutation, and doing so would refetch the whole run for no reason.
 */
export function usePushBranch(runId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (request: { findingIds: string[]; branch: string; token: string; openPullRequest: boolean }) =>
      pushBranch(runId!, request),
    onSuccess: (result) => {
      toast.success(`${result.branch} 브랜치를 올렸습니다`, {
        description: result.pr_url
          ? "풀 리퀘스트를 열었습니다."
          : `${result.applied.length}건이 반영되었습니다.`,
      });
      // The run itself is untouched; only its list row's timestamp is stale.
      void client.invalidateQueries({ queryKey: keys.runs() });
    },
    onError: (error) => toast.error("브랜치를 올릴 수 없습니다", { description: describeError(error) }),
  });
}

/**
 * Stop a running scan.
 *
 * Invalidates the run rather than patching a status in: the worker decides what
 * the run becomes -- `cancelled`, with whatever it had found -- and guessing that
 * here would show a state the server may not agree with.
 */
export function useCancelRun(runId: string | null) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => cancelRun(runId!),
    onSuccess: () => {
      toast.info("검사를 중단했습니다", { description: "그때까지 찾은 것은 그대로 남습니다." });
      void client.invalidateQueries({ queryKey: keys.run(runId!) });
      void client.invalidateQueries({ queryKey: keys.runs() });
    },
    onError: (error) => toast.error("검사를 중단할 수 없습니다", { description: describeError(error) }),
  });
}
