"use client";

import { Code2, Map, MoreHorizontal, Sliders, Workflow, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import KnowledgePanel from "@/features/knowledge/KnowledgePanel";
import GraphPane from "@/features/trace/GraphPane";
import { useCentreView, type CentreView } from "@/lib/run/selection";
import { useRunId } from "@/lib/run/use-run-id";
import { useRunStream } from "@/lib/run/stream";
import EditorPane from "./EditorPane";
import StateView from "./StateView";

/** The two views anyone comes here for. */
const TABS = [
  { id: "code", label: "코드", icon: Code2 },
  { id: "graph", label: "에이전트 구조", icon: Workflow },
] as const;

/**
 * Views that exist and are not offered.
 *
 * A map of the code's own call graph and a step-by-step dump of LangGraph's state
 * are things you go looking for when you are debugging the agent. Standing on the
 * tab strip beside 코드 they were two thirds of the choices on screen, and neither
 * answers a question anyone opened this page with.
 *
 * Behind the one overflow button on the tab strip, and shown as a dismissible tab
 * while open so nobody is stranded on a view with no way back. They were reachable
 * from the command palette until the palette went; a menu is one control rather
 * than a whole keyboard surface.
 */
const HIDDEN = [
  { id: "map", label: "코드 관계도", icon: Map, title: "코드 관계도 열기" },
  { id: "state", label: "단계별 상태", icon: Sliders, title: "단계별 상태 열기" },
] as const;

/**
 * The centre: the code, and the agent that read it.
 *
 * Two tabs. It had four, which is the whole of what the surface could show rather
 * than the part worth showing -- and a tab strip is a claim that each of its
 * entries is somewhere you might want to be.
 *
 * Only the active view is mounted. Two of these are React Flow canvases and one
 * is Monaco; keeping them all alive means laying out graphs nobody is looking at.
 */
export default function CentrePane() {
  const [runId] = useRunId();
  const [view, setView] = useCentreView();
  const { phase } = useRunStream();

  const running = phase === "running" || phase === "starting" || phase === "paused";
  const hidden = HIDDEN.find((each) => each.id === view);

  return (
    <div className="flex h-full min-h-0 flex-col bg-surface">
      <Tabs
        value={view}
        onValueChange={(next) => void setView(next as CentreView)}
        className="shrink-0 gap-0"
      >
        <header className="flex h-9 shrink-0 items-center border-b border-line px-1.5">
          <TabsList variant="line" className="h-full gap-0 bg-transparent p-0">
            {TABS.map((each) => (
              <TabsTrigger key={each.id} value={each.id} className="h-full gap-1.5 px-2.5 text-xs font-medium">
                <each.icon className="size-3.5" />
                {each.label}
                {/* A run in flight is the reason to look at the graph, so the tab
                    says so rather than waiting to be found. */}
                {each.id === "graph" && running && view !== "graph" && (
                  <span className="size-1.5 animate-pulse rounded-full bg-accent" />
                )}
              </TabsTrigger>
            ))}
            {hidden && (
              <TabsTrigger value={hidden.id} className="h-full gap-1.5 px-2.5 text-xs font-medium">
                <hidden.icon className="size-3.5" />
                {hidden.label}
              </TabsTrigger>
            )}
          </TabsList>

          {hidden && (
            <Button
              size="icon-xs"
              variant="ghost"
              className="ml-1"
              aria-label={`${hidden.label} 닫기`}
              onClick={() => void setView("code")}
            >
              <X className="text-ink-faint" />
            </Button>
          )}

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button size="icon-xs" variant="ghost" className="ml-auto" aria-label="다른 보기">
                <MoreHorizontal className="text-ink-faint" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
              {HIDDEN.map((each) => (
                <DropdownMenuItem key={each.id} onSelect={() => void setView(each.id)} className="gap-2">
                  <each.icon className="size-3.5" />
                  <span className="text-xs">{each.label}</span>
                </DropdownMenuItem>
              ))}
            </DropdownMenuContent>
          </DropdownMenu>
        </header>
      </Tabs>

      <div className="min-h-0 flex-1">
        {view === "code" && <EditorPane runId={runId} />}
        {view === "graph" && <GraphPane />}
        {view === "map" && <KnowledgePanel />}
        {view === "state" && <StateView />}
      </div>
    </div>
  );
}
