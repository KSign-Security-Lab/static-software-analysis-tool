"use client";

import { HelpCircle } from "lucide-react";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { perspectiveFor } from "@/lib/workbench/perspectives";

/**
 * The strip that says which of the five tools you are looking at.
 *
 * Without it the app is four grey panels and a rail: every surface has the
 * same anatomy, so the shell that makes them feel like one application is
 * exactly what stops them being told apart. The name and the sentence are
 * always visible; the ordered steps are one click away, because they are worth
 * reading once and in the way afterwards.
 */
export default function PerspectiveHeader() {
  const current = perspectiveFor(usePathname());
  if (!current) return null;

  return (
    <header className="flex h-10 shrink-0 items-center gap-3 border-b border-line bg-surface px-3">
      <current.icon className="size-4 shrink-0 text-accent-ink" />
      <h1 className="shrink-0 text-md font-semibold text-ink-strong">{current.label}</h1>
      <p className="truncate text-sm text-ink-muted">{current.note}</p>

      <Popover>
        <PopoverTrigger asChild>
          <Button size="xs" variant="ghost" className="ml-auto shrink-0 text-ink-muted">
            <HelpCircle />
            사용법
          </Button>
        </PopoverTrigger>
        <PopoverContent align="end" className="w-96 p-0">
          <div className="border-b border-line px-3 py-2">
            <p className="text-sm font-semibold text-ink-strong">{current.label}</p>
            <p className="mt-0.5 text-xs text-ink-muted">{current.purpose}</p>
          </div>
          <ol className="space-y-2 p-3">
            {current.steps.map((step, index) => (
              <li key={step} className="flex gap-2.5">
                <span className="mt-px grid size-5 shrink-0 place-items-center rounded-full bg-accent-wash font-mono text-2xs font-semibold text-accent-ink">
                  {index + 1}
                </span>
                <span className="text-xs leading-relaxed text-ink">{step}</span>
              </li>
            ))}
          </ol>
        </PopoverContent>
      </Popover>
    </header>
  );
}
