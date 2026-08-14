"use client";

import { Contrast, HelpCircle, PanelBottom, PanelLeft, PanelRight } from "lucide-react";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { PERSPECTIVES, hrefFor, perspectiveFor } from "@/lib/workbench/perspectives";
import { PANE_LABEL, type PaneId } from "@/lib/workbench/store";
import { useWorkbench } from "@/lib/workbench/store-provider";

/**
 * The 64px rail: the four perspectives, and the controls that belong to no
 * surface in particular.
 *
 * Named, not only drawn. Four glyphs and a tooltip is a navigation you can use
 * once you already know it, and these are four quite different tools sharing
 * one shell -- an icon cannot say which inspects code and which reads a
 * finished run's reasoning. The tooltip keeps the sentence that will not fit.
 *
 * The folds and the theme were here, then moved to the title bar, and are back.
 * The title bar is gone on 검사: at 1600 it was `SSAT │ 검사 │ 1,270px of
 * nothing │ 사용법 ▣▣▣`, a 36px row whose middle was empty for its whole life,
 * with a second 36px run strip beneath it. These four controls are the only
 * things on it that were genuinely global, and a rail that already runs the
 * full height has room for them at its foot -- which is also where an eye looks
 * for settings rather than for places to go.
 *
 * Fixed width and a flex sibling of the panel group, not a zero-min panel: the
 * group sizes in percentages, so a rail expressed as one would breathe with
 * the window, which is the standard way these layouts end up unable to hold a
 * fixed strip.
 */
export default function ActivityBar() {
  const pathname = usePathname();
  const params = useSearchParams();
  const current = perspectiveFor(pathname);
  const { setTheme } = useTheme();
  const collapsed = useWorkbench((s) => s.collapsed);
  const togglePane = useWorkbench((s) => s.togglePane);
  // Where a title bar still exists, it keeps these. See the note above the foot.
  const chrome = current?.chrome ?? true;

  return (
    <nav aria-label="화면" className="flex w-16 shrink-0 flex-col items-center gap-px border-r border-line bg-surface py-1">
      {/* The wordmark and the foot exist only where the title bar does not.
          On the surfaces that still have one they would be a second copy of
          controls already up there, so those stay byte-identical. */}
      {!chrome && (
        <span
          className="grid h-8 w-full shrink-0 place-items-center font-mono text-xs font-bold tracking-tight text-accent-ink"
          aria-hidden
        >
          SSAT
        </span>
      )}

      {PERSPECTIVES.map((p) => {
        const active = current?.id === p.id;
        return (
          <Tooltip key={p.id}>
            <TooltipTrigger asChild>
              <Link
                href={hrefFor(p.id, params)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative grid w-full justify-items-center gap-1 border-l-2 border-transparent py-2 transition-colors",
                  "text-ink-faint hover:bg-surface-2 hover:text-ink focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset",
                  // A left bar and a weight change, not a filled block. The
                  // wash is the strongest colour on the page and spending it
                  // on the thing you are already looking at leaves nothing for
                  // the thing you are meant to notice.
                  active && "border-l-accent bg-surface-2 text-ink-strong",
                )}
              >
                <p.icon className={cn("size-[18px]", active && "text-accent-ink")} />
                <span className="text-2xs leading-none font-medium">{p.label}</span>
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right">
              <span className="font-medium">{p.label}</span>
              <span className="ml-2 text-ink-faint">{p.note}</span>
            </TooltipContent>
          </Tooltip>
        );
      })}

      {/* The foot. `mt-auto` rather than a spacer div, so it sits against the
          floor at every window height without reserving anything. */}
      {!chrome && (
      <div className="mt-auto flex w-full flex-col items-center gap-0.5 pt-2">
        {current && (
          <Popover>
            <PopoverTrigger asChild>
              <Button size="icon-xs" variant="ghost" aria-label="사용법">
                <HelpCircle className="text-ink-faint" />
              </Button>
            </PopoverTrigger>
            <PopoverContent side="right" align="end" className="w-96 p-0">
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

        {/* Only the panes this surface has. Offering to unfold a pane that does
            not exist reveals a panel whose entire content is a sentence saying
            this screen does not have one. */}
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
      </div>
      )}
    </nav>
  );
}

const PANES: { id: PaneId; icon: typeof PanelLeft }[] = [
  { id: "side", icon: PanelLeft },
  { id: "dock", icon: PanelBottom },
  { id: "inspector", icon: PanelRight },
];
