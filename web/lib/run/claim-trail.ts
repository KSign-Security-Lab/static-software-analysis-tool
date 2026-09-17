"use client";

import { useMemo } from "react";

import type { UiFinding } from "@/lib/model/finding";
import { claimOf, trailOf, unitsOf, type Exchange } from "@/lib/trace/process";
import { useGraphShape, useThreads } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";

export function useClaimTrail(finding: UiFinding | undefined): Exchange[] {
  const [runId] = useRunId();
  const threads = useThreads(runId);
  const shape = useGraphShape();

  return useMemo(() => {
    if (!finding?.chunkIds.length) return [];
    const units = unitsOf(threads.data?.threads ?? [], shape.data?.steps ?? [], null);
    const wanted = new Set(finding.chunkIds);
    const unit = units.find((each) => wanted.has(each.id));
    return unit ? trailOf(unit, claimOf(finding)).exchanges : [];
  }, [finding, threads.data, shape.data]);
}
