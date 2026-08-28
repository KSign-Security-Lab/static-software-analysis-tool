"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useState } from "react";

export interface DockTab {
  id: string;
  label: string;
  /** Rendered right of the label: a finding count, a span count. */
  badge?: React.ReactNode;
  content: React.ReactNode;
}

/**
 * The bottom panel's tab strip.
 *
 * Content is mounted for the active tab only. These panels hold a virtualized
 * span tree and two React Flow canvases, and keeping the inactive ones alive
 * means measuring and laying out graphs nobody can see.
 *
 * Uncontrolled by default -- one surface's tab strip is nobody else's business,
 * and F2-A has a single tab that nothing links to. 검사 controls it, because
 * there the tab decides whether you are looking at the problems, the pipeline or
 * the call record, and that is worth being able to send someone.
 */
export default function DockTabs({
  tabs,
  value,
  onValueChange,
}: {
  tabs: DockTab[];
  /** Set both to drive the strip from outside -- 검사 keeps it in the URL. */
  value?: string;
  onValueChange?: (next: string) => void;
}) {
  const [chosen, setChosen] = useState<string | null>(null);

  // The first tab is the surface's default, so ordering says what matters here.
  // Unset, or set to something this surface does not have, falls back to it
  // rather than to an empty panel.
  const active = tabs.find((t) => t.id === (value ?? chosen)) ?? tabs[0];

  return (
    <section className="flex h-full min-h-0 flex-col bg-surface">
      {/* `shrink-0`, not `flex-1`: the tab strip is a header. Letting it grow
          pushed the panel's content to the bottom of the dock, under a screen
          of empty space. */}
      <Tabs
        value={active?.id}
        onValueChange={onValueChange ?? setChosen}
        className="shrink-0 gap-0"
      >
        <header className="flex h-9 shrink-0 items-center border-b border-line px-1.5">
          <TabsList variant="line" className="h-full gap-0 bg-transparent p-0">
            {tabs.map((tab) => (
              <TabsTrigger
                key={tab.id}
                value={tab.id}
                className="h-full gap-1.5 px-2.5 text-2xs font-semibold tracking-wide uppercase"
              >
                {tab.label}
                {tab.badge != null && <span className="text-ink-faint normal-case">{tab.badge}</span>}
              </TabsTrigger>
            ))}
          </TabsList>
        </header>
      </Tabs>
      <div className="min-h-0 flex-1 overflow-auto">{active?.content}</div>
    </section>
  );
}
