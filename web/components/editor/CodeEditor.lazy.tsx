"use client";

import dynamic from "next/dynamic";

import { Skeleton } from "@/components/ui/skeleton";

/**
 * The editor, client-only.
 *
 * Monaco measures the DOM on mount, so it cannot be server-rendered. Wrapped
 * once here rather than at each usage site -- there used to be a `dynamic()`
 * call per page, including two for components that never touched the DOM and
 * were only paying for a chunk boundary.
 *
 * The skeleton fills the pane exactly. One that is shorter makes the panel
 * group recompute when the real editor swaps in, and the layout jumps.
 */
const CodeEditor = dynamic(() => import("./CodeEditor"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full flex-col gap-2 p-4">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
      <Skeleton className="h-4 w-3/5" />
      <Skeleton className="mt-2 h-4 w-1/4" />
    </div>
  ),
});

export default CodeEditor;
