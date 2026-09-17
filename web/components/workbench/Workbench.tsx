"use client";

import { useCallback, useRef, type ReactNode } from "react";
import type { Layout, PanelImperativeHandle, PanelSize } from "react-resizable-panels";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import ActivityBar from "@/components/workbench/ActivityBar";
import PerspectiveHeader from "@/components/workbench/PerspectiveHeader";
import { CpgSourceProvider } from "@/features/cpg/provider";
import { cookieValue, layoutFor, type PaneLayout, type StoredLayout } from "@/lib/workbench/layout-cookie";
import { perspective, type PerspectiveId } from "@/lib/workbench/perspectives";
import type { PaneId } from "@/lib/workbench/store";
import { useWorkbench } from "@/lib/workbench/store-provider";
import { useBeforePaint } from "@/lib/workbench/use-before-paint";

export interface WorkbenchProps {
  perspective: PerspectiveId;
  stored: StoredLayout;
  children: ReactNode;
  side: ReactNode;
  dock: ReactNode;
  inspector: ReactNode;
}

function usePane(id: PaneId) {
  const registerPanel = useWorkbench((s) => s.registerPanel);
  const setCollapsed = useWorkbench((s) => s.setCollapsed);
  const handle = useRef<PanelImperativeHandle | null>(null);

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

  const onResize = useCallback((size: PanelSize) => setCollapsed(id, size.asPercentage <= 0), [id, setCollapsed]);

  return { panelRef, onResize, collapse };
}

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

export default function Workbench({
  perspective: current,
  stored,
  children,
  side,
  dock,
  inspector,
}: WorkbenchProps) {
  const initial: PaneLayout = layoutFor(stored, current);

  const latest = useRef<PaneLayout>(initial);

  const sidePane = usePane("side");
  const dockPane = usePane("dock");
  const inspectorPane = usePane("inspector");
  const panes = { side: sidePane, dock: dockPane, inspector: inspectorPane };

  useBeforePaint(() => {
    for (const [id, pane] of Object.entries(panes) as [PaneId, typeof sidePane][]) {
      const axis = id === "dock" ? initial.v : initial.h;
      if (axis[id] === 0) pane.collapse();
    }
  }, []);

  const persist = useCallback(
    (axis: "h" | "v", sizes: Layout) => {
      latest.current = { ...latest.current, [axis]: sizes };
      document.cookie = cookieValue({
        ...stored,
        [current]: latest.current,
      });
    },
    [current, stored],
  );

  return (
    <CpgSourceProvider>
        <div className="flex h-dvh flex-col overflow-hidden bg-bg text-ink">
          {perspective(current).chrome && <PerspectiveHeader />}

          <div className="flex min-h-0 min-w-0 flex-1">
            <ActivityBar />

            <ResizablePanelGroup
              orientation="horizontal"
              defaultLayout={initial.h}
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

              <ResizableHandle />

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
            </ResizablePanelGroup>
          </div>
        </div>
    </CpgSourceProvider>
  );
}
