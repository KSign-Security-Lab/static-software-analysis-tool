"use client";

import { Contrast, HelpCircle } from "lucide-react";
import type { ReactNode } from "react";
import { useTheme } from "next-themes";

import Rail, { HowToUse } from "@/components/nav/Rail";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useForgetMissingRun } from "@/lib/run/forget-missing";
import { RunStreamProvider } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";

export default function InspectShell({ children }: { children: ReactNode }) {
  const [runId] = useRunId();
  useForgetMissingRun();
  const { setTheme } = useTheme();

  return (
    <RunStreamProvider runId={runId}>
      <div className="fixed inset-0 flex overflow-hidden bg-bg text-ink">
        <Rail
          wordmark
          foot={
            <>
              <Popover>
                <PopoverTrigger asChild>
                  <Button size="icon-xs" variant="ghost" aria-label="사용법">
                    <HelpCircle className="text-ink-faint" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent side="right" align="end" className="w-96 p-0">
                  <HowToUse />
                </PopoverContent>
              </Popover>

              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    size="icon-xs"
                    variant="ghost"
                    aria-label="테마 전환"
                    onClick={() =>
                      setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light")
                    }
                  >
                    <Contrast className="text-ink-faint" />
                  </Button>
                </TooltipTrigger>
                <TooltipContent side="right">테마 전환</TooltipContent>
              </Tooltip>
            </>
          }
        />
        <main className="flex min-h-0 min-w-0 flex-1 flex-col">{children}</main>
      </div>
    </RunStreamProvider>
  );
}
