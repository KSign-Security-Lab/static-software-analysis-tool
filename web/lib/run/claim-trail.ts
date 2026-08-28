"use client";

import { useMemo } from "react";

import type { UiFinding } from "@/lib/model/finding";
import { claimOf, trailOf, unitsOf, type Exchange } from "@/lib/trace/process";
import { useGraphShape, useThreads } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * The agents that produced one finding, in the order they ran.
 *
 * `trailOf` has computed this since the transcript learned to scope itself to a
 * claim, and nothing ever showed it *as* a chain -- it was only ever used to
 * filter a transcript, so the reader could see the conversation but had to
 * reconstruct who contributed what from a tree of collapsed rows. "Which agents
 * were involved in this decision, and what did each of them conclude" is the
 * first question anyone asks of a machine-made claim, and the answer was
 * derivable rather than stated.
 *
 * Every chunk the claim came out of, not just the representative's: a merged
 * finding was reported by two units, and a re-run reuses cached ones, so the unit
 * this run actually recorded may not be the one the row is filed under.
 *
 * Empty is a real answer and means the join found nothing -- a finding served from
 * the cross-run cache has no calls in *this* run at all. The caller says so
 * rather than showing an empty list.
 */
export function useClaimTrail(finding: UiFinding | undefined): Exchange[] {
  const [runId] = useRunId();
  const threads = useThreads(runId);
  const shape = useGraphShape();

  return useMemo(() => {
    if (!finding?.chunkIds.length) return [];
    // No node scope: this is the chain that produced the claim, not the part of
    // it that happens to survive whatever the graph is filtered to.
    const units = unitsOf(threads.data?.threads ?? [], shape.data?.steps ?? [], null);
    const wanted = new Set(finding.chunkIds);
    const unit = units.find((each) => wanted.has(each.id));
    return unit ? trailOf(unit, claimOf(finding)).exchanges : [];
  }, [finding, threads.data, shape.data]);
}
