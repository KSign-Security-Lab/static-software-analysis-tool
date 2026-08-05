"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useWorkbench } from "@/lib/workbench/store-provider";

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
 * The active tab lives in the workbench store rather than the URL: it is
 * arrangement, not what you are looking at, and putting it in the address bar
 * would make every panel switch a history entry.
 *
 * Content is mounted for the active tab only. These panels hold a virtualized
 * span tree and a React Flow canvas, and keeping the inactive ones alive means
 * measuring and laying out graphs nobody can see.
 */
export default function DockTabs({ tabs }: { tabs: DockTab[] }) {
  const dockTab = useWorkbench((s) => s.dockTab);
  const setDockTab = useWorkbench((s) => s.setDockTab);

  const active = tabs.find((t) => t.id === dockTab) ?? tabs[0];

  return (
    <section className="flex h-full min-h-0 flex-col bg-surface">
      <Tabs value={active?.id} onValueChange={setDockTab} className="min-h-0 flex-1 gap-0">
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
