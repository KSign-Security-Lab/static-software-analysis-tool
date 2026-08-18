"use client";

import { Code2, Workflow } from "lucide-react";
import { parseAsStringLiteral, useQueryState } from "nuqs";

import EditorPane from "@/features/agent/EditorPane";
import RunControls from "@/features/agent/RunControls";
import GraphPane from "@/features/trace/GraphPane";
import { cn } from "@/lib/utils";

/**
 * The widest region, and what it can hold.
 *
 * Two tabs and the run's controls on one row. The row exists for the tabs; the
 * controls ride its empty right half, which is why 검사 lost a 36px strip
 * without losing anything that was on it.
 *
 * 구조 was a full-window overlay for exactly as long as it took to notice that
 * the thing it needed -- width -- is what the centre already has. The overlay
 * cost a portal, a backdrop, an Escape handler, a focus trap it never had, and
 * three days of the drawing not appearing at all.
 */
const TABS = ["code", "graph"] as const;

export default function CentrePane() {
  const [tab, setTab] = useQueryState(
    "view",
    // `code` is the default and drops out of the address bar, so a bare link
    // opens on the file rather than on the machinery.
    parseAsStringLiteral(TABS).withDefault("code").withOptions({ history: "replace" }),
  );

  return (
    <section className="flex h-full min-h-0 min-w-0 flex-col bg-surface">
      <div className="flex h-9 shrink-0 items-center gap-1 border-b border-line px-1.5">
        <Tab active={tab === "code"} icon={Code2} onClick={() => void setTab("code")}>
          코드
        </Tab>
        <Tab active={tab === "graph"} icon={Workflow} onClick={() => void setTab("graph")}>
          구조
        </Tab>

        <span className="ml-auto" />
        <RunControls />
      </div>

      {/* Both stay mounted. Monaco is expensive to rebuild and React Flow
          re-measures from zero every time it mounts, which is the whole of the
          `#004` blank-canvas bug -- switching tabs should not re-run either. */}
      <div className={cn("min-h-0 min-w-0 flex-1", tab !== "code" && "hidden")}>
        <EditorPane />
      </div>
      <div className={cn("relative min-h-0 min-w-0 flex-1", tab !== "graph" && "hidden")}>
        <GraphPane direction="LR" />
      </div>
    </section>
  );
}

function Tab({
  active,
  icon: Icon,
  onClick,
  children,
}: {
  active: boolean;
  icon: typeof Code2;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
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
