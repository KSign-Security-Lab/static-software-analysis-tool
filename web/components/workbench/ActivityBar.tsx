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
