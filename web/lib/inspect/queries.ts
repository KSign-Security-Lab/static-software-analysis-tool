"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { describeError } from "@/lib/api/client";
import { cancelRun } from "@/lib/api/control";
import { downloadArchive, previewPatch, pushBranch, savePatch } from "@/lib/api/patch";
import { keys } from "@/lib/query/keys";
import { useRunStream } from "@/lib/run/stream";

export function usePatchPreview(runId: string | null) {
  return useMutation({
    mutationFn: (findingIds: string[]) => previewPatch(runId!, findingIds),
    onError: (error) => toast.error("패치를 만들 수 없습니다", { description: describeError(error) }),
  });
}

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
      void client.invalidateQueries({ queryKey: keys.runs() });
    },
    onError: (error) => toast.error("브랜치를 올릴 수 없습니다", { description: describeError(error) }),
  });
}

export function useCancelRun(runId: string | null) {
  const client = useQueryClient();
  const { markCancelling, clearCancelling } = useRunStream();
  return useMutation({
    mutationFn: () => cancelRun(runId!),
    onMutate: () => markCancelling(),
    onSuccess: () => {
      toast.info("검사를 중단하는 중입니다", {
        description: "지금 하던 분석만 끝내고 멈춥니다. 그때까지 찾은 것은 그대로 남습니다.",
      });
      void client.invalidateQueries({ queryKey: keys.summary(runId!) });
      void client.invalidateQueries({ queryKey: keys.runs() });
    },
    onError: (error) => {
      clearCancelling();
      void client.invalidateQueries({ queryKey: keys.summary(runId!) });
      toast.error("검사를 중단할 수 없습니다", { description: describeError(error) });
    },
  });
}
