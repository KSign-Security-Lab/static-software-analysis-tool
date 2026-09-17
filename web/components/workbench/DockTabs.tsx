"use client";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useState } from "react";

export interface DockTab {
  id: string;
  label: string;
  badge?: React.ReactNode;
  content: React.ReactNode;
}

export default function DockTabs({
  tabs,
  value,
  onValueChange,
}: {
  tabs: DockTab[];
  value?: string;
  onValueChange?: (next: string) => void;
}) {
  const [chosen, setChosen] = useState<string | null>(null);

  const active = tabs.find((t) => t.id === (value ?? chosen)) ?? tabs[0];

  return (
    <section className="flex h-full min-h-0 flex-col bg-surface">
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
