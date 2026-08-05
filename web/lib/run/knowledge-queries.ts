"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchKnowledge } from "@/lib/api/knowledge";
import { keys } from "@/lib/query/keys";

/**
 * The code's graph for one run.
 *
 * `retry: false` because the only expected failure is a 404, which means the
 * run was never indexed -- an answer, not an error, and asking again will not
 * change it.
 */
export function useKnowledge(runId: string | null) {
  return useQuery({
    queryKey: keys.knowledge(runId ?? ""),
    queryFn: ({ signal }) => fetchKnowledge(runId!, { signal }),
    enabled: Boolean(runId),
    retry: false,
    gcTime: 30 * 60 * 1000,
  });
}
