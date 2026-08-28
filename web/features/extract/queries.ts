"use client";

import { useQuery } from "@tanstack/react-query";

import { analyzeFunctions } from "@/lib/api/ssat";

/**
 * The SSAT extractor's own per-function AST and DFG.
 *
 * Reuses the CPG `/analyze` already returned rather than recompiling: Joern is
 * the expensive part and it has already run.
 */
export function usePipeline(cpg: unknown | null) {
  return useQuery({
    queryKey: ["ssat", "pipeline", cpg ? "ready" : "none"],
    queryFn: () => analyzeFunctions(cpg),
    enabled: Boolean(cpg),
    staleTime: Infinity,
  });
}
