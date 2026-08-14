"use client";

import { Ellipsis } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import WhoAmI from "@/features/agent/WhoAmI";
import { countOf, useRunControls } from "@/lib/run/controls";
import { phaseFor } from "@/lib/run/reduce";
import { useRun } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useGraphShape } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * The two settings, behind one trigger.
 *
 * Breakpoints and the owner name were two of six controls in the run strip's
 * corner, all the same size and weight as the one that starts a run costing
 * minutes and money -- so nothing in the group looked more important than
 * anything else. Neither is an action: one configures the next run, the other
 * filters a list. That is what belongs behind a `⋯`.
 */
export default function RunMenu({ className }: { className?: string }) {
  const [runId] = useRunId();
  const { breakpoints, toggleBreakpoint } = useRunControls();
  const { phase: streamed } = useRunStream();
  const run = useRun(runId);
  const shape = useGraphShape();

  const phase = phaseFor(streamed, run.data?.status);
  const running = phase === "running" || phase === "starting";
  const set = countOf(breakpoints);

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="icon-xs" variant="ghost" aria-label="검사 설정" className={cn("relative", className)}>
          <Ellipsis className="text-ink-muted" />
          {set > 0 && <span className="absolute top-0.5 right-0.5 size-1.5 rounded-full bg-alt" aria-hidden />}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-72 p-0">
        <div className="flex items-center gap-2 border-b border-line px-3 py-2">
          <span className="text-2xs text-ink-faint">이름</span>
          <WhoAmI />
        </div>

        {/* Not before there is a run to stop. On an empty workbench it offered
            to set a breakpoint in an inspection that cannot be started. */}
        {runId && (
          <>
            <div className="flex items-baseline gap-2 border-b border-line px-3 py-2">
              <span className="text-2xs text-ink-strong">중단점{set > 0 ? ` ${set}` : ""}</span>
              <span className="min-w-0 flex-1 text-2xs text-ink-faint">
                {running ? "실행 중에는 바꿀 수 없습니다" : "노드 앞/뒤에서 멈춥니다"}
              </span>
            </div>
            <ScrollArea className="h-64">
              <ul className={cn("p-1", running && "pointer-events-none opacity-50")}>
                {(shape.data?.steppable ?? []).map((name) => (
                  <li key={name} className="flex items-center gap-2 rounded-sm px-2 py-1 hover:bg-surface-2">
                    <span className="flex-1 truncate font-mono text-2xs">{name}</span>
                    {(["before", "after"] as const).map((when) => (
                      <span key={when} className="flex items-center gap-1">
                        <Checkbox
                          id={`bp-${when}-${name}`}
                          checked={breakpoints[when].includes(name)}
                          onCheckedChange={() => toggleBreakpoint(name, when)}
                        />
                        <Label htmlFor={`bp-${when}-${name}`} className="text-2xs text-ink-faint">
                          {when === "before" ? "앞" : "뒤"}
                        </Label>
                      </span>
                    ))}
                  </li>
                ))}
              </ul>
            </ScrollArea>
          </>
        )}
      </PopoverContent>
    </Popover>
  );
}
