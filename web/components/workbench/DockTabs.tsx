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
 * The bottom dock's tab strip.
 *
 * The active tab is component state: it is arrangement, not what you are looking
 * at, so it belongs neither in the URL nor in a store.
 *
 * Content is mounted for the active tab only. These panels hold a virtualized
 * span tree and a React Flow canvas, and keeping the inactive ones alive means
 * measuring and laying out graphs nobody can see.
 */
export default function DockTabs({ tabs }: { tabs: DockTab[] }) {
  // Local state. It lived in a global store so the shell could read it, and the
  // shell never did -- one surface's tab strip is nobody else's business.
  const [chosen, setChosen] = useState<string | null>(null);

  // The first tab is the surface's default, so ordering says what matters here.
  // Unset, or set to something this surface does not have, falls back to it rather
  // than to an empty panel.
  const active = tabs.find((t) => t.id === chosen) ?? tabs[0];

  return (
    <section className="flex h-full min-h-0 flex-col bg-surface">
      {/* `shrink-0`, not `flex-1`: the tab strip is a header. Letting it grow
          pushed the panel's content to the bottom of the dock, under a screen
          of empty space. */}
      <Tabs value={active?.id} onValueChange={setChosen} className="shrink-0 gap-0">
        <header className="flex h-8 shrink-0 items-center border-b border-line px-1.5">
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
