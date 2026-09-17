"use client";

import { useQuery } from "@tanstack/react-query";

import { analyzeFunctions } from "@/lib/api/ssat";

export function usePipeline(cpg: unknown | null) {
  return useQuery({
    queryKey: ["ssat", "pipeline", cpg ? "ready" : "none"],
    queryFn: () => analyzeFunctions(cpg),
    enabled: Boolean(cpg),
    staleTime: Infinity,
  });
}
