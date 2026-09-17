"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";

const StepGraph = dynamic(() => import("./StepGraph"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full place-items-center p-4">
      <Skeleton className="h-24 w-2/3" />
    </div>
  ),
});

export default StepGraph;
