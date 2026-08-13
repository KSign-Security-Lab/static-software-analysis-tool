"use client";

import dynamic from "next/dynamic";

import NodeDetail from "@/features/machine/NodeDetail";
import { useAgentSheet } from "@/features/trace/state";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

const GraphPane = dynamic(() => import("@/features/trace/GraphPane"), { ssr: false });
const StateView = dynamic(() => import("@/features/agent/StateView"), { ssr: false });
const KnowledgePanel = dynamic(() => import("@/features/knowledge/KnowledgePanel"), { ssr: false });

/**
 * The machinery, over the screen rather than instead of it.
 *
 * This was a second workspace, and the two did not match: one rendered four
 * panels and a rail of problems, the other five and a rail of files, so crossing
 * between them rearranged the window and the same product looked like two
 * applications sharing a header.
 *
 * The instinct was right -- the checker's machinery was taking space from the
 * answer -- but the fix is where it sits, not whether you are allowed to see it.
 * A dialog leaves every panel behind it exactly as it was: same widths, same
 * selection, same scroll. You come back to where you were because you never
 * left.
 *
 * The canvas needs width, which is why it was a centre tab for so long. Here it
 * gets the whole window.
 */
export default function AgentSheet() {
  const [open, setOpen] = useAgentSheet();

  return (
    <Dialog open={open} onOpenChange={(next) => void setOpen(next || null)}>
      <DialogContent
        showCloseButton
        className="flex h-[88vh] w-[92vw] max-w-none flex-col gap-0 overflow-hidden p-0 sm:max-w-none"
      >
        <DialogHeader className="shrink-0 border-b border-line px-3 py-2">
          <DialogTitle className="text-sm">에이전트</DialogTitle>
          <DialogDescription className="text-2xs">
            검사가 지나가는 길입니다. 노드를 누르면 그 노드가 무엇인지 아래에 나오고, 중단점을 걸면 다음 실행이
            거기서 멈춥니다.
          </DialogDescription>
        </DialogHeader>

        <Tabs defaultValue="graph" className="flex min-h-0 flex-1 flex-col gap-0">
          <TabsList variant="line" className="shrink-0 gap-0 border-b border-line bg-transparent px-2">
            <TabsTrigger value="graph" className="text-xs">
              구조
            </TabsTrigger>
            <TabsTrigger value="state" className="text-xs">
              단계별 상태
            </TabsTrigger>
            <TabsTrigger value="map" className="text-xs">
              코드 관계도
            </TabsTrigger>
          </TabsList>

          <TabsContent value="graph" className="flex min-h-0 flex-1 flex-col">
            <div className="min-h-0 flex-[3]">
              <GraphPane />
            </div>
            <div className="min-h-0 flex-[2] border-t border-line">
              <NodeDetail />
            </div>
          </TabsContent>
          <TabsContent value="state" className="min-h-0 flex-1">
            <StateView />
          </TabsContent>
          <TabsContent value="map" className="min-h-0 flex-1">
            <KnowledgePanel />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}
