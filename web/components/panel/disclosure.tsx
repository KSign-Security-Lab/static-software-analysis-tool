"use client";

import { ChevronRight } from "lucide-react";

import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { cn } from "@/lib/utils";

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
