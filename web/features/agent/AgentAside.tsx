"use client";

import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from "@/components/ui/resizable";
import GraphPane from "@/features/trace/GraphPane";
import Inspector from "./Inspector";

/**
 * The right column: the agent's structure, and the one thing you picked.
 *
 * The structure is drawn top to bottom here, which is the point of it being here
 * at all -- a tall narrow column suits a vertical pipeline, and it sits *beside*
 * the code rather than stacked under it competing for the same height. It shared
 * the bottom panel with the record before, and three regions in one column meant
 * none of them had room.
 *
 * It is fixed reference, so it is above rather than below: it does not change as
 * you read, and the thing that does change should be the one nearer your eye when
 * you are clicking through a list.
 *
 * Clicking a node selects it, and the half underneath says what it is -- the same
 * rule as everywhere else on this surface: something picks, the inspector details.
 */
export default function AgentAside() {
  return (
    <ResizablePanelGroup orientation="vertical" className="bg-surface">
      <ResizablePanel id="structure" collapsible collapsedSize="0" minSize="15" defaultSize="40">
        <GraphPane direction="TB" />
      </ResizablePanel>

      <ResizableHandle />

      <ResizablePanel id="detail" minSize="25">
        <Inspector />
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}
