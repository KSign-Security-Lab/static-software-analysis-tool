"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { describeError } from "@/lib/api/client";
import { fetchGraph, resumeRun, type ResumeOptions } from "@/lib/api/control";
import { fetchPrompts, resetPrompt, savePrompt } from "@/lib/api/prompts";
import { fetchCheckpoints, fetchSpans, fetchThreads, replaySpan } from "@/lib/api/trace";
import { EMPTY_SUMMARY } from "@/lib/api/types";
import { keys } from "@/lib/query/keys";

const enabled = (runId: string | null): runId is string => Boolean(runId);

/** The graph's shape is a property of the code; it changes when the server restarts. */
export function useGraphShape() {
  return useQuery({
    queryKey: keys.graph(),
    queryFn: ({ signal }) => fetchGraph({ signal }),
    staleTime: Infinity,
    gcTime: Infinity,
  });
}

export function useSpans(runId: string | null) {
  return useQuery({
    queryKey: keys.spans(runId ?? ""),
    queryFn: ({ signal }) => fetchSpans(runId!, { signal }),
    enabled: enabled(runId),
    // Structural sharing is the point of the default: a refetched span array
    // keeps identity for unchanged rows, so the tree, the Gantt scale and the
    // per-node stats do not all recompute on every checkpoint.
    placeholderData: (previous) => previous,
  });
}

export function useThreads(runId: string | null) {
  return useQuery({
    queryKey: keys.threads(runId ?? ""),
    queryFn: ({ signal }) => fetchThreads(runId!, { signal }),
    enabled: enabled(runId),
    placeholderData: (previous) => previous,
  });
}

export function useCheckpoints(runId: string | null, full: boolean) {
  return useQuery({
    queryKey: keys.checkpoints(runId ?? "", full),
    queryFn: ({ signal }) => fetchCheckpoints(runId!, full, { signal }),
    enabled: enabled(runId),
    // Keyed by `full`, so toggling back to the summary does not throw away the
    // copy already in hand.
    placeholderData: (previous) => previous,
  });
}

export function usePrompts() {
  return useQuery({
    queryKey: keys.prompts(),
    queryFn: ({ signal }) => fetchPrompts({ signal }).then((r) => r.prompts),
    staleTime: Infinity,
  });
}

/** Both prompt mutations return the whole list, so nothing needs refetching. */
export function useSavePrompt() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ name, text }: { name: string; text: string }) => savePrompt(name, text),
    onSuccess: (result) => client.setQueryData(keys.prompts(), result.prompts),
    onError: (error) => toast.error("프롬프트를 저장할 수 없습니다", { description: describeError(error) }),
  });
}

export function useResetPrompt() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => resetPrompt(name),
    onSuccess: (result) => client.setQueryData(keys.prompts(), result.prompts),
    onError: (error) => toast.error("프롬프트를 되돌릴 수 없습니다", { description: describeError(error) }),
  });
}

/**
 * Re-run one recorded model call.
 *
 * Writes nothing -- not the run, not the trace, not the report -- so there is
 * deliberately no cache invalidation here. That is the pane's contract and the
 * reason it is safe to press repeatedly.
 */
export function useReplay(runId: string | null) {
  return useMutation({
    mutationFn: ({ spanId, system, user }: { spanId: string; system?: string | null; user?: string | null }) =>
      replaySpan(runId!, spanId, { system, user }),
    onError: (error) => toast.error("다시 실행할 수 없습니다", { description: describeError(error) }),
  });
}

/** Resume, fork, re-run, abort -- all the same endpoint. */
export function useResume(runId: string | null, ensureAttached: () => Promise<void>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (options: ResumeOptions) => {
      // The server ends the stream when a run finishes, so anything that makes
      // it move again has to be listening first.
      if (options.action !== "abort") await ensureAttached();
      return resumeRun(runId!, options);
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.summary(runId!) }),
    onError: (error) => toast.error("이어서 실행할 수 없습니다", { description: describeError(error) }),
  });
}

export { EMPTY_SUMMARY };
