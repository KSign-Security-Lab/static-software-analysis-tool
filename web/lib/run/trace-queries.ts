"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { describeError } from "@/lib/api/client";
import { fetchGraph, resumeRun, type ResumeOptions } from "@/lib/api/control";
import { fetchPrompts } from "@/lib/api/prompts";
import { fetchSpans, fetchThreads } from "@/lib/api/trace";
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
    // Held across a refetch, dropped when there is no run: keeping the last
    // run's data as a placeholder is the point while one is in flight, and a
    // lie once it has been deleted -- the pane went on showing a conversation
    // that no longer existed, beside an empty workbench.
    placeholderData: (previous) => (runId ? previous : undefined),
  });
}

export function useThreads(runId: string | null) {
  return useQuery({
    queryKey: keys.threads(runId ?? ""),
    queryFn: ({ signal }) => fetchThreads(runId!, { signal }),
    enabled: enabled(runId),
    // Held across a refetch, dropped when there is no run: keeping the last
    // run's data as a placeholder is the point while one is in flight, and a
    // lie once it has been deleted -- the pane went on showing a conversation
    // that no longer existed, beside an empty workbench.
    placeholderData: (previous) => (runId ? previous : undefined),
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
