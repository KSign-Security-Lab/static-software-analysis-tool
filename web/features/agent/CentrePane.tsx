"use client";

import { Code2, Workflow } from "lucide-react";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import GraphPane from "@/features/trace/GraphPane";
import { useRunId } from "@/lib/run/use-run-id";
import { useRunStream } from "@/lib/run/stream";
import { cn } from "@/lib/utils";
import EditorPane from "./EditorPane";
import { useCentreView } from "./state";

const VIEWS = [
  { id: "code", label: "코드", icon: Code2 },
  { id: "graph", label: "에이전트 구조", icon: Workflow },
] as const;

/**
 * The centre: the code, or the run that read it.
 *
 * These were two routes and it was the wrong seam. They are one run seen two
 * ways -- the same explorer beside them, the same 문제 and 구조 지도 beneath,
 * an inspector that already swapped by what you had selected -- so moving
 * between them meant a navigation, a lost open file, and a redirect on 검사
 * 실행 to put you where the run was legible. A tab does that without leaving
 * the page, which is the whole point of going back and forth between what the
 * agent decided and how it got there.
 *
 * Only the active view is mounted. One holds Monaco and the other a React Flow
 * canvas; keeping both alive means laying out a graph nobody is looking at.
 */
export default function CentrePane() {
  const [runId] = useRunId();
  const [view, setView] = useCentreView();
  const { phase } = useRunStream();

  const running = phase === "running" || phase === "starting" || phase === "paused";

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      <Tabs value={view} onValueChange={(next) => void setView(next as typeof view)} className="shrink-0 gap-0">
        <header className="flex h-8 shrink-0 items-center border-b border-line px-1.5">
          <TabsList variant="line" className="h-full gap-0 bg-transparent p-0">
            {VIEWS.map((each) => (
              <TabsTrigger key={each.id} value={each.id} className="h-full gap-1.5 px-2.5 text-xs font-medium">
                <each.icon className="size-3.5" />
                {each.label}
                {/* A run in flight is the reason to look at the other tab, so
                    the other tab says so rather than waiting to be found. */}
                {each.id === "graph" && running && view !== "graph" && (
                  <span className="size-1.5 animate-pulse rounded-full bg-accent" />
                )}
              </TabsTrigger>
            ))}
          </TabsList>
        </header>
      </Tabs>

      <div className={cn("min-h-0 flex-1")}>
        {view === "code" ? <EditorPane runId={runId} /> : <GraphPane />}
      </div>
    </div>
  );
}
