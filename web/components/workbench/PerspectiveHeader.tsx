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

const PANES: { id: PaneId; icon: typeof PanelLeft }[] = [
  { id: "side", icon: PanelLeft },
  { id: "dock", icon: PanelBottom },
  { id: "inspector", icon: PanelRight },
];

/**
 * The title bar: where you are, and the window controls.
 *
 * There used to be a status strip along the foot of the window as well, carrying
 * the run id, the phase and a standing "로컬 기록 · 외부 전송 없음". The phase is
 * at the top of the pane that shows the run now, where it means something, and
 * the rest was a permanent band of text nobody needed twice -- so the strip is
 * gone and these controls are the only chrome left around the panels.
 *
 * It carries the wordmark in a cell exactly as wide as the rail, so the rail,
 * this bar and the panel headers below all meet on the same two lines rather
 * than stacking three bands of three different heights. Same height as a panel
 * header, for the same reason.
 *
 * The panel folds and the theme live here rather than at the foot of the rail. They
 * are window controls, not places to go -- and putting them here leaves the rail
 * doing one job.
 *
 * The folds no longer advertise a keybinding: ⌘B and ⌘J went with the keyboard
 * layer, which existed to feed a command palette this app does not have.
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

      {/* The perspective's one-line pitch used to sit beside this. It never
          changed and never told anyone anything twice; it is in 사용법 now, with
          the rest of the explaining. */}
      {current && (
        <h1 className="min-w-0 flex-1 truncate px-3 text-sm font-semibold text-ink-strong">{current.label}</h1>
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

        {PANES.map(({ id, icon: Icon }) => (
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
            <TooltipContent side="bottom">{PANE_LABEL[id]} 접기/펼치기</TooltipContent>
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
