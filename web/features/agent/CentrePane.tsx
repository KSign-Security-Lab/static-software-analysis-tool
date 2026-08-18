"use client";

import { Code2, GitCompare, Route, Workflow } from "lucide-react";

import EditorPane from "@/features/agent/EditorPane";
import RunControls from "@/features/agent/RunControls";
import FixView from "@/features/agent/views/FixView";
import ProcessView from "@/features/agent/views/ProcessView";
import GraphPane from "@/features/trace/GraphPane";
import { useCentreTab, type CentreTab } from "@/features/agent/centre-tab";
import { useOpenFinding } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * The widest region, and the four things that need width.
 *
 * Everything here was somewhere narrower and worse for it. The patch was a
 * unified diff in a 400px column, where a `-` and a `+` on the same statement
 * land four wrapped rows apart. A call's prompt runs to 3,628 characters --
 * eighty lines of scrolling there, thirty-six here. The drawing was a
 * full-window overlay because no pane was big enough, which cost a portal, a
 * backdrop, an Escape handler and three days of it not appearing at all.
 *
 * The tab strip carries the run's controls at its right end. That row exists
 * for the tabs and its right half was empty, which is how 검사 lost a 36px
 * strip without losing anything that was on it.
 */
export default function CentrePane() {
  const [runId] = useRunId();
  const [tab, setTab] = useCentreTab();
  const finding = useOpenFinding(runId) ?? null;

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col bg-surface">
      <div className="flex h-9 shrink-0 items-center gap-1 border-b border-line px-1.5">
        <Tab id="code" tab={tab} icon={Code2} onPick={setTab}>
          코드
        </Tab>
        <Tab id="fix" tab={tab} icon={GitCompare} onPick={setTab}>
          수정
        </Tab>
        <Tab id="process" tab={tab} icon={Route} onPick={setTab}>
          과정
        </Tab>
        <Tab id="graph" tab={tab} icon={Workflow} onPick={setTab}>
          구조
        </Tab>

        <span className="ml-auto" />
        <RunControls />
      </div>

      {/* The editor and the drawing stay mounted. Monaco is expensive to
          rebuild, and React Flow re-measures from zero on every mount -- which
          is the whole of the `#004` blank-canvas bug. The other two are cheap
          and are built on demand. */}
      <div className={cn("min-h-0 min-w-0 flex-1", tab !== "code" && "hidden")}>
        <EditorPane />
      </div>
      <div className={cn("relative min-h-0 min-w-0 flex-1", tab !== "graph" && "hidden")}>
        <GraphPane direction="TB" />
      </div>
      {tab === "fix" && (
        <div className="min-h-0 min-w-0 flex-1">
          <FixView finding={finding} />
        </div>
      )}
      {tab === "process" && (
        <div className="min-h-0 min-w-0 flex-1">
          <ProcessView finding={finding} />
        </div>
      )}
    </section>
  );
}

function Tab({
  id,
  tab,
  icon: Icon,
  onPick,
  children,
}: {
  id: CentreTab;
  tab: CentreTab;
  icon: typeof Code2;
  onPick: (next: CentreTab) => void;
  children: React.ReactNode;
}) {
  const active = tab === id;
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={() => onPick(id)}
      className={cn(
        "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs transition-colors",
        active ? "bg-surface-2 text-ink-strong" : "text-ink-muted hover:bg-surface-2 hover:text-ink",
      )}
    >
      <Icon className={cn("size-3.5", active && "text-accent-ink")} />
      {children}
    </button>
  );
}
