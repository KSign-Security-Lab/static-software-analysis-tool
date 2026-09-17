"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { describeError } from "@/lib/api/client";
import { fetchGraph, resumeRun, type ResumeOptions } from "@/lib/api/control";
import { fetchPrompts } from "@/lib/api/prompts";
import { fetchSpans, fetchThreads } from "@/lib/api/trace";
import { keys } from "@/lib/query/keys";

const enabled = (runId: string | null): runId is string => Boolean(runId);

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
    placeholderData: (previous) => (runId ? previous : undefined),
  });
}

export function useThreads(runId: string | null) {
  return useQuery({
    queryKey: keys.threads(runId ?? ""),
    queryFn: ({ signal }) => fetchThreads(runId!, { signal }),
    enabled: enabled(runId),
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

export function useResume(runId: string | null, ensureAttached: () => Promise<void>) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: async (options: ResumeOptions) => {
      if (options.action !== "abort") await ensureAttached();
      return resumeRun(runId!, options);
    },
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.summary(runId!) }),
    onError: (error) => toast.error("이어서 실행할 수 없습니다", { description: describeError(error) }),
  });
}
