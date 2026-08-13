"use client";

import { ChevronRight } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

/**
 * A row that opens.
 *
 * There were five of these: a `Fold` for asides, three near-identical row
 * triggers at the file, unit and step levels of the run tree, and another in the
 * dock -- each with its own chevron, its own hover, and its own idea of how far
 * to indent what it revealed. They drifted the way five copies do, and the tree
 * ended up with three different left rhythms stacked inside each other.
 *
 * `tone` is the only thing that varies, because the levels genuinely differ in
 * weight: a file heads a group, a step is one line of a list, an aside is
 * something you are being told you may ignore.
 */
export function Disclosure({
  open,
  onOpenChange,
  label,
  aside,
  tone = "row",
  className,
  children,
}: {
  open?: boolean;
  onOpenChange?: (next: boolean) => void;
  label: React.ReactNode;
  /** Pushed to the right of the trigger: an outcome, a count, a cost. */
  aside?: React.ReactNode;
  tone?: "group" | "row" | "aside";
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <Collapsible open={open} onOpenChange={onOpenChange} className={className}>
      <CollapsibleTrigger
        className={cn(
          "group/row flex w-full min-w-0 items-center gap-1.5 text-left transition-colors",
          tone !== "aside" && "px-2.5 py-1.5 hover:bg-surface-2",
          tone === "group" && "font-medium text-ink-strong",
          tone === "row" && "text-ink-muted",
          tone === "aside" && "gap-1 font-mono text-2xs text-ink-faint hover:text-ink-muted",
        )}
      >
        <ChevronRight
          className={cn(
            "size-3 shrink-0 text-ink-faint transition-transform group-data-[state=open]/row:rotate-90",
          )}
          aria-hidden
        />
        <span className="min-w-0 flex-1 truncate">{label}</span>
        {aside && <span className="shrink-0">{aside}</span>}
      </CollapsibleTrigger>
      <CollapsibleContent>{children}</CollapsibleContent>
    </Collapsible>
  );
}
