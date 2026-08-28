"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";

/**
 * The graph, client-only.
 *
 * React Flow measures the DOM on mount, so it cannot be server-rendered. One
 * wrapper, one import site: the old studio dynamic-imported the canvas and its
 * provider separately, which let the provider render before the consumer's
 * chunk had arrived.
 */
const StepGraph = dynamic(() => import("./StepGraph"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full place-items-center p-4">
      <Skeleton className="h-24 w-2/3" />
    </div>
  ),
});

export default StepGraph;
