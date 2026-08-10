"use client";

import type { ReactNode } from "react";

import { CpgSourceProvider } from "@/features/cpg/provider";
import { RunStreamProvider } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import ActivityBar from "./ActivityBar";
import PerspectiveHeader from "./PerspectiveHeader";

/**
 * The shell: a rail, a header, and three regions at fixed sizes.
 *
 * It was a resizable panel group with a persisted layout, collapse handles, a
 * command palette and a keybinding layer -- an IDE, for a surface where nobody
 * writes code. All of that is gone, and this is flexbox.
 *
 * Removing the splitters is also how the resizing bug got fixed. Panel geometry was
 * measured with a ResizeObserver, nested inside two more (Monaco's and React
 * Flow's); the three re-entered each other, the browser dropped the notifications
 * it could not deliver, and a drag or a fold went unreported. There is nothing left
 * to observe: the sizes are declared in CSS and the browser lays them out once.
 *
 * Sizes are fixed on purpose. Every one was a number in a cookie that a drag could
 * put anywhere, including zero, and "the panel is gone and I do not know why" was
 * the result.
 *
 * Narrow windows *stack*; they never hide. The first version of this used
 * `hidden lg:block`, which deleted the run's own output below 1024px -- and browser
 * zoom shrinks the CSS viewport, so zooming in far enough made the chat disappear
 * on a monitor that had plenty of room for it. A region a reader cannot reach is
 * worse than a cramped one, and the whole point of this surface is the two panes
 * you read side by side.
 */
export default function Shell({
  children,
  side,
  dock,
  inspector,
}: {
  children: ReactNode;
  side: ReactNode;
  dock: ReactNode;
  inspector: ReactNode;
}) {
  const [runId] = useRunId();

  return (
    // The stream sits above the routes, so exactly one EventSource exists per tab
    // and it survives navigation between surfaces. See lib/run/stream.tsx.
    <RunStreamProvider runId={runId}>
      <CpgSourceProvider>
        <div className="grid h-dvh grid-rows-[auto_1fr] overflow-hidden bg-bg text-ink">
          <PerspectiveHeader />

          <div className="flex min-h-0 min-w-0">
            <ActivityBar />

            {/* Below `lg` this column scrolls and each region keeps a workable
                minimum. From `lg` it is a row and the regions divide the window. */}
            <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
              <aside className="min-h-64 shrink-0 border-b border-line lg:min-h-0 lg:w-56 lg:border-r lg:border-b-0">
                {side}
              </aside>

              <div className="flex min-h-[36rem] min-w-0 flex-1 flex-col lg:min-h-0">
                <div className="min-h-0 flex-1">{children}</div>
                <div className="h-52 shrink-0 border-t border-line">{dock}</div>
              </div>

              <div className="min-h-[36rem] shrink-0 border-t border-line lg:min-h-0 lg:w-[26rem] lg:border-t-0 lg:border-l xl:w-[30rem]">
                {inspector}
              </div>
            </div>
          </div>
        </div>
      </CpgSourceProvider>
    </RunStreamProvider>
  );
}
