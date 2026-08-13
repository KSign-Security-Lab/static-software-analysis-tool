"use client";

import { usePathname } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, type ReactNode } from "react";
import type { Layout, PanelImperativeHandle, PanelSize } from "react-resizable-panels";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import ActivityBar from "@/components/workbench/ActivityBar";
import PerspectiveHeader from "@/components/workbench/PerspectiveHeader";
import { CpgSourceProvider } from "@/features/cpg/provider";
import { useForgetMissingRun } from "@/lib/run/forget-missing";
import { RunStreamProvider } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import { cookieValue, layoutFor, widths, type PaneLayout, type StoredLayout } from "@/lib/workbench/layout-cookie";
import { isInspectSpace, type PerspectiveId } from "@/lib/workbench/perspectives";
import type { PaneId } from "@/lib/workbench/store";
import { useWorkbench } from "@/lib/workbench/store-provider";

/**
 * The workbench: activity bar, explorer, centre, dock, inspector.
 *
 * The panel tree is the only place geometry lives. `main` nests its own
 * vertical group so the dock spans the editor width and the explorer runs full
 * height -- the arrangement that makes a file tree usable while the dock is
 * tall, and the reason the dock is not a sibling of `side`.
 *
 * Sizes arrive as props from the server, read out of a cookie, so the first
 * paint is already correct. See lib/workbench/layout-cookie.ts for why not
 * localStorage and why not the library's own persistence.
 */

export interface WorkbenchProps {
  perspective: PerspectiveId;
  stored: StoredLayout;
  children: ReactNode;
  side: ReactNode;
  dock: ReactNode;
  inspector: ReactNode;
}

// useLayoutEffect warns when React renders a client component on the server.
// The work below has to happen before paint, so it cannot just become useEffect.
const useBeforePaint = typeof window === "undefined" ? useEffect : useLayoutEffect;

/** Registers the handle with the store and mirrors folds back out of it. */
function usePane(id: PaneId) {
  const registerPanel = useWorkbench((s) => s.registerPanel);
  const setCollapsed = useWorkbench((s) => s.setCollapsed);
  const handle = useRef<PanelImperativeHandle | null>(null);

  // Registration only. Asking the handle anything here crashes the app.
  //
  // A ref callback runs during commit, and on React's StrictMode remount --
  // effects destroyed, then re-created -- that is *before* the group has
  // registered itself again. `isCollapsed()` looks the group up by id, so it
  // threw `Group … not found` out of the commit phase, which React cannot
  // recover from: the whole tree unmounted to the error boundary. The page
  // still server-rendered perfectly and then sat there, hydrated by nothing,
  // with every button inert. Only in dev, which is why a production build
  // never showed it.
  //
  // The mirror does not need the handle anyway: the fold state came from the
  // cookie on the server, and `onResize` keeps it true from then on.
  const panelRef = useCallback(
    (next: PanelImperativeHandle | null) => {
      handle.current = next;
      registerPanel(id, next);
    },
    [id, registerPanel],
  );

  const collapse = useCallback(() => {
    handle.current?.collapse();
    setCollapsed(id, true);
  }, [id, setCollapsed]);

  // A drag to zero folds a panel without going through togglePane, so the
  // mirror has to follow the panel rather than the other way round.
  const onResize = useCallback((size: PanelSize) => setCollapsed(id, size.asPercentage <= 0), [id, setCollapsed]);

  return { panelRef, onResize, collapse };
}

/**
 * Sizes are passed as strings on purpose.
 *
 * v4 inverted v3's convention: a bare number is now *pixels*, and a string
 * without a unit is a percentage. `minSize={12}` therefore means 12px, which
 * silently fought the 18% default layout until the group gave up and
 * re-solved it against content width -- the explorer came out at 5.5%.
 */
const SIZE = {
  sideMin: "12",
  sideMax: "40",
  mainMin: "30",
  centreMin: "20",
  dockMin: "10",
  inspectorMin: "14",
  inspectorMax: "45",
  collapsed: "0",
} as const;

export default function Workbench({ perspective, stored, children, side, dock, inspector }: WorkbenchProps) {
  const [runId] = useRunId();
  /**
   * Whether this route has a right-hand pane.
   *
   * 검사 is a rail, an editor and the finding under it -- there is no fourth
   * thing, and a panel rendered anyway is an empty column asking to be filled.
   *
   * Decided here rather than in the layout, which is a server component: a
   * layout is not re-rendered for a client-side navigation within its own
   * segment, so switching 검사 → 에이전트 kept whichever answer the first
   * request happened to produce, and the record pane never appeared.
   */
  const showInspector = !isInspectSpace(usePathname());
  // Here because the shell is what owns which run the tab is on, and because it
  // is mounted exactly once -- a dozen components each deciding to drop the id
  // would be a dozen writes to the address bar.
  useForgetMissingRun();
  const initial: PaneLayout = layoutFor(stored, perspective);

  // Not state: it is only ever read when writing the cookie back, and making
  // it state would re-render the whole tree on every drag.
  const latest = useRef<PaneLayout>(initial);

  const sidePane = usePane("side");
  const dockPane = usePane("dock");
  const inspectorPane = usePane("inspector");
  const panes = { side: sidePane, dock: dockPane, inspector: inspectorPane };

  /**
   * Restore folds.
   *
   * A stored 0 says the panel was folded, but the group will not server-render
   * `flex-grow: 0` -- it substitutes 1, which paints a 16px sliver instead of
   * nothing. So the fold is applied imperatively, in a layout effect, which
   * runs after commit and before the browser paints: correct on the first
   * frame the user sees, with no flash to notice.
   *
   * Sizes are not folds, so only zeroes are touched; everything non-zero came
   * through `defaultLayout` and is already right in the HTML.
   */
  useBeforePaint(() => {
    for (const [id, pane] of Object.entries(panes) as [PaneId, typeof sidePane][]) {
      const axis = id === "dock" ? initial.v : initial.h;
      if (axis[id] === 0) pane.collapse();
    }
    // Once, from the server's answer. Later folds go through the panel handles.
  }, []);

  const horizontal = useMemo(() => widths(initial.h, showInspector), [showInspector, initial.h]);

  const persist = useCallback(
    (axis: "h" | "v", sizes: Layout) => {
      latest.current = { ...latest.current, [axis]: sizes };
      // `onLayoutChanged` already waits for the pointer to be released, so
      // there is nothing left to debounce.
      document.cookie = cookieValue({
        ...stored,
        [perspective]: latest.current,
      });
    },
    [perspective, stored],
  );

  return (
    // The stream sits above the panels and outside the routes, so exactly one
    // EventSource exists per tab and it survives navigation between
    // perspectives. See lib/run/stream.tsx for why that is load-bearing.
    <RunStreamProvider runId={runId}>
      <CpgSourceProvider>
        <div className="grid h-dvh grid-rows-[auto_1fr] overflow-hidden bg-bg text-ink">
          <PerspectiveHeader />

          {/*
            `min-w-0` is load-bearing, and its absence was visible as the right
            pane being cut off by the edge of the window.

            A grid item's automatic minimum size is its *min-content* width, so
            this row could not be narrower than the widest thing any panel held --
            measured at 1768px inside a 1600px cell, which the grid's
            `overflow-hidden` then clipped rather than scrolled. The panels
            themselves already carry `min-width: 0`; it does them no good while the
            row they sit in is free to grow. So the panel group solved its
            percentages against 1704px of imaginary space and put the inspector's
            right edge 168px past the window.

            Which panel misbehaved depended on what was on screen, which is why it
            read as an intermittent layout glitch rather than as a rule.
          */}
          <div className="flex min-h-0 min-w-0">
            <ActivityBar />

            <ResizablePanelGroup
              orientation="horizontal"
              defaultLayout={horizontal}
              onLayoutChanged={(sizes) => persist("h", sizes)}
            >
              <ResizablePanel
                id="side"
                collapsible
                collapsedSize={SIZE.collapsed}
                minSize={SIZE.sideMin}
                maxSize={SIZE.sideMax}
                panelRef={sidePane.panelRef}
                onResize={sidePane.onResize}
              >
                {side}
              </ResizablePanel>

              <ResizableHandle />

              <ResizablePanel id="main" minSize={SIZE.mainMin}>
                <ResizablePanelGroup
                  orientation="vertical"
                  defaultLayout={initial.v}
                  onLayoutChanged={(sizes) => persist("v", sizes)}
                >
                  <ResizablePanel id="centre" minSize={SIZE.centreMin}>
                    {children}
                  </ResizablePanel>

                  <ResizableHandle />

                  <ResizablePanel
                    id="dock"
                    collapsible
                    collapsedSize={SIZE.collapsed}
                    minSize={SIZE.dockMin}
                    panelRef={dockPane.panelRef}
                    onResize={dockPane.onResize}
                  >
                    {dock}
                  </ResizablePanel>
                </ResizablePanelGroup>
              </ResizablePanel>

              {showInspector && <ResizableHandle />}

              {showInspector && (
                <ResizablePanel
                  id="inspector"
                  collapsible
                  collapsedSize={SIZE.collapsed}
                  minSize={SIZE.inspectorMin}
                  maxSize={SIZE.inspectorMax}
                  panelRef={inspectorPane.panelRef}
                  onResize={inspectorPane.onResize}
                >
                  {inspector}
                </ResizablePanel>
              )}
            </ResizablePanelGroup>
          </div>
        </div>
      </CpgSourceProvider>
    </RunStreamProvider>
  );
}
