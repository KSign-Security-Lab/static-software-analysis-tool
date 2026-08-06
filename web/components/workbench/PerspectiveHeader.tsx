"use client";

import { Contrast, HelpCircle, PanelBottom, PanelLeft, PanelRight } from "lucide-react";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { perspectiveFor } from "@/lib/workbench/perspectives";
import { PANE_LABEL, type PaneId } from "@/lib/workbench/store";
import { useWorkbench } from "@/lib/workbench/store-provider";

const PANES: { id: PaneId; icon: typeof PanelLeft; key: string }[] = [
  { id: "side", icon: PanelLeft, key: "⌘B" },
  { id: "dock", icon: PanelBottom, key: "⌘J" },
  { id: "inspector", icon: PanelRight, key: "⌘⌥B" },
];

/**
 * The title bar: who you are, where you are, and the window controls.
 *
 * It carries the wordmark in a cell exactly as wide as the rail, so the rail,
 * this bar and the panel headers below all meet on the same two lines rather
 * than stacking three bands of three different heights. Same height as a panel
 * header, for the same reason.
 *
 * The panel folds and the theme live here rather than at the foot of the rail.
 * They are window controls, not places to go -- and putting them here leaves
 * the rail doing one job and stops this bar being a sentence with a lone
 * button marooned at the far end of it.
 */
export default function PerspectiveHeader() {
  const current = perspectiveFor(usePathname());
  const { setTheme } = useTheme();
  const collapsed = useWorkbench((s) => s.collapsed);
  const togglePane = useWorkbench((s) => s.togglePane);

  return (
    <header className="flex h-9 shrink-0 items-center border-b border-line bg-surface">
      <span
        className="grid h-full w-16 shrink-0 place-items-center border-r border-line font-mono text-xs font-bold tracking-tight text-accent-ink"
        aria-hidden
      >
        SSAT
      </span>

      {current && (
        <div className="flex min-w-0 flex-1 items-baseline gap-2 px-3">
          <h1 className="shrink-0 text-sm font-semibold text-ink-strong">{current.label}</h1>
          <p className="truncate text-xs text-ink-faint">{current.note}</p>
        </div>
      )}

      <div className="ml-auto flex shrink-0 items-center gap-0.5 pr-2">
        {current && (
          <Popover>
            <PopoverTrigger asChild>
              <Button size="xs" variant="ghost" className="text-ink-muted">
                <HelpCircle />
                사용법
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" className="w-96 p-0">
              <div className="border-b border-line px-3 py-2">
                <p className="text-sm font-semibold text-ink-strong">{current.label}</p>
                <p className="mt-0.5 text-xs text-ink-muted">{current.purpose}</p>
              </div>
              <ol className="space-y-2 p-3">
                {current.steps.map((step, index) => (
                  <li key={step} className="flex gap-2.5">
                    <span className="mt-px grid size-5 shrink-0 place-items-center rounded-full bg-accent-wash font-mono text-2xs font-semibold text-accent-ink">
                      {index + 1}
                    </span>
                    <span className="text-xs leading-relaxed text-ink">{step}</span>
                  </li>
                ))}
              </ol>
            </PopoverContent>
          </Popover>
        )}

        <span className="mx-1 h-4 w-px bg-line" />

        {PANES.map(({ id, icon: Icon, key }) => (
          <Tooltip key={id}>
            <TooltipTrigger asChild>
              <Button
                size="icon-xs"
                variant="ghost"
                aria-label={`${PANE_LABEL[id]} 접기/펼치기`}
                aria-pressed={!collapsed[id]}
                onClick={() => togglePane(id)}
              >
                <Icon className={cn(collapsed[id] ? "text-ink-faint" : "text-ink-muted")} />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">
              {PANE_LABEL[id]} 접기/펼치기<span className="ml-2 text-ink-faint">{key}</span>
            </TooltipContent>
          </Tooltip>
        ))}

        <Tooltip>
          <TooltipTrigger asChild>
            <Button
              size="icon-xs"
              variant="ghost"
              aria-label="테마 전환"
              onClick={() => setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light")}
            >
              <Contrast className="text-ink-muted" />
            </Button>
          </TooltipTrigger>
          <TooltipContent side="bottom">테마 전환</TooltipContent>
        </Tooltip>
      </div>
    </header>
  );
}
