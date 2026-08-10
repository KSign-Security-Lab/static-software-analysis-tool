"use client";

import { Sheet, SheetContent } from "@/components/ui/sheet";
import SpanInspector from "@/features/trace/SpanInspector";
import type { PromptRow, TraceSpan } from "@/lib/api/types";

/**
 * Editing one call's prompt and running it again.
 *
 * A sheet, because it is an action taken *on* something you found in 진행 rather
 * than a view of the run. As a permanent right-hand pane it was empty until you
 * had clicked a call, and it held a quarter of the window open to say so.
 */
export default function PromptSheet({
  runId,
  span,
  prompts,
  open,
  onOpenChange,
}: {
  runId: string | null;
  span: TraceSpan | null;
  prompts: PromptRow[];
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      {/* Wide: it holds two prompts and a side-by-side diff of the answers. */}
      <SheetContent side="right" className="w-[min(46rem,100vw)] gap-0 p-0 sm:max-w-none">
        <SpanInspector runId={runId} span={span} prompts={prompts} />
      </SheetContent>
    </Sheet>
  );
}
