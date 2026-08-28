"use client";

import { Contrast, HelpCircle, PanelBottom, PanelLeft, PanelRight } from "lucide-react";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";

import Rail, { HowToUse } from "@/components/nav/Rail";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { perspectiveFor } from "@/lib/workbench/perspectives";
import { PANE_LABEL, type PaneId } from "@/lib/workbench/store";
import { useWorkbench } from "@/lib/workbench/store-provider";

/**
 * The workbench's rail: the shared surface list, plus this shell's own controls.
 *
 * The pane folds are the only thing here that belongs to the workbench rather
 * than to the application, which is why the surface list itself is `Rail` --
 * shared with 검사's shell, so the two cannot drift into two navigations for one
 * app.
 *
 * The foot appears only where a surface has no title bar to carry these instead.
 * `PerspectiveHeader` holds the same three controls up there, and rendering both
 * would put two copies of the theme switch on one screen. 벤치마크 is the one
 * workbench surface with `chrome: false`, so it is the one that needs the foot.
 */
export default function ActivityBar() {
  const current = perspectiveFor(usePathname());
  const { setTheme } = useTheme();
  const collapsed = useWorkbench((s) => s.collapsed);
  const togglePane = useWorkbench((s) => s.togglePane);
  const chrome = current?.chrome ?? true;

  if (chrome) return <Rail />;

  return (
    <Rail
      foot={
        <>
          <Popover>
            <PopoverTrigger asChild>
              <Button size="icon-xs" variant="ghost" aria-label="사용법">
                <HelpCircle className="text-ink-faint" />
              </Button>
            </PopoverTrigger>
            <PopoverContent side="right" align="end" className="w-96 p-0">
              <HowToUse />
            </PopoverContent>
          </Popover>

          {/* Only the panes this surface has. Offering to unfold a pane that
              does not exist reveals a panel whose entire content is a sentence
              saying this screen does not have one. */}
          {PANES.filter(({ id }) => current?.panes.includes(id)).map(({ id, icon: Icon }) => (
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
              <TooltipContent side="right">{PANE_LABEL[id]} 접기/펼치기</TooltipContent>
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
                <Contrast className="text-ink-faint" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">테마 전환</TooltipContent>
          </Tooltip>
        </>
      }
    />
  );
}

const PANES: { id: PaneId; icon: typeof PanelLeft }[] = [
  { id: "side", icon: PanelLeft },
  { id: "dock", icon: PanelBottom },
  { id: "inspector", icon: PanelRight },
];
