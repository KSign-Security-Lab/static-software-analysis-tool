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

/**
 * The rail, and one region.
 *
 * That is the whole shell. Every pane 검사 used to have was a place to put
 * something the reader had to hold in their head while looking somewhere else --
 * the file tree while reading a finding, the finding while reading its
 * reasoning -- and the answer to each turned out to be that it belongs *inside*
 * the thing it is about rather than beside it.
 *
 * The event stream lives here, above the route, so exactly one EventSource
 * exists per tab and it survives the stage changing under it. That is
 * load-bearing: the stream cannot be replayed, so an EventSource remounted when
 * scanning becomes results would miss every event between.
 */
export default function InspectShell({ children }: { children: ReactNode }) {
  const [runId] = useRunId();
  // Here because the shell owns which run the tab is on, and it is mounted
  // exactly once -- a component per stage each deciding to drop a dead id would
  // be three writes to the address bar.
  useForgetMissingRun();
  const { setTheme } = useTheme();

  return (
    <RunStreamProvider runId={runId}>
      {/* `fixed inset-0`, not `h-dvh`, and it is load-bearing.

          In flow, the findings list's overflow escaped into the document's own
          scroll box: past the end of the list the *window* scrolled another
          2,600px, taking the rail with it and leaving a full-width black void.
          `overflow-hidden` here did not stop it and neither did `overflow:
          hidden` on html or body -- measured, both of them. Out of flow, the
          document has nothing to scroll: `documentElement.scrollHeight` goes
          from 3566 to 950 against a 950px viewport.

          The box is the same one `h-dvh` produced, so nothing inside changes. */}
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

              {/* No fold buttons: there are no panes to fold. */}
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
