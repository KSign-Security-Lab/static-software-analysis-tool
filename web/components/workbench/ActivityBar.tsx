"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useTheme } from "next-themes";
import { Contrast, PanelBottom, PanelLeft, PanelRight } from "lucide-react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { PERSPECTIVES, hrefFor, perspectiveFor } from "@/lib/workbench/perspectives";
import { useWorkbench } from "@/lib/workbench/store-provider";
import { PANE_LABEL, type PaneId } from "@/lib/workbench/store";

const PANE_ICON: Record<PaneId, typeof PanelLeft> = {
  side: PanelLeft,
  dock: PanelBottom,
  inspector: PanelRight,
};

const PANE_KEY: Record<PaneId, string> = {
  side: "⌘B",
  dock: "⌘J",
  inspector: "⌘⌥B",
};

function Item({
  label,
  hint,
  active,
  children,
  ...props
}: {
  label: string;
  hint?: string;
  active?: boolean;
  children: React.ReactNode;
} & React.ComponentProps<"button">) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          aria-label={label}
          className={cn(
            "relative grid size-10 place-items-center rounded-md text-ink-muted transition-colors",
            "hover:bg-surface-2 hover:text-ink focus-visible:ring-2 focus-visible:ring-ring",
            active && "text-ink-strong",
          )}
          {...props}
        >
          {children}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right">
        {label}
        {hint ? <span className="ml-2 text-ink-faint">{hint}</span> : null}
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * The 68px rail. Perspectives on top, panel folds and the theme underneath.
 *
 * The perspectives are named, not only drawn. Five glyphs and a tooltip is a
 * navigation you can use once you know it, and this app is five quite
 * different tools sharing a shell -- an icon cannot say which one inspects
 * code and which one reads a finished run's reasoning. The tooltips stay for
 * the sentence that will not fit.
 *
 * Fixed width and a flex sibling of the panel group, not a zero-min panel:
 * the group sizes in percentages, so a rail expressed as one would breathe
 * with the window and is the standard way these layouts end up unable to hold
 * a fixed strip.
 */
export default function ActivityBar() {
  const pathname = usePathname();
  const params = useSearchParams();
  const { setTheme } = useTheme();
  const current = perspectiveFor(pathname);

  const collapsed = useWorkbench((s) => s.collapsed);
  const togglePane = useWorkbench((s) => s.togglePane);

  return (
    <nav
      aria-label="화면"
      className="flex w-[68px] shrink-0 flex-col items-center gap-0.5 border-r border-line bg-surface py-2"
    >
      <span className="mb-2 font-mono text-sm leading-none font-bold tracking-tight text-accent-ink" aria-hidden>
        SSAT
      </span>

      {PERSPECTIVES.map((p) => {
        const active = current?.id === p.id;
        return (
          <Tooltip key={p.id}>
            <TooltipTrigger asChild>
              <Link
                href={hrefFor(p.id, params)}
                aria-current={active ? "page" : undefined}
                className={cn(
                  "relative grid w-[60px] justify-items-center gap-0.5 rounded-md py-1.5 text-ink-muted transition-colors",
                  "hover:bg-surface-2 hover:text-ink focus-visible:ring-2 focus-visible:ring-ring",
                  active && "bg-accent-wash text-accent-ink",
                )}
              >
                {/* The active marker is a bar, not only a colour. */}
                {active && (
                  <span aria-hidden className="absolute top-1.5 -left-1 h-8 w-0.5 rounded-full bg-accent-ink" />
                )}
                <p.icon className="size-[18px]" />
                <span className="text-[11px] leading-tight font-medium">{p.label}</span>
              </Link>
            </TooltipTrigger>
            <TooltipContent side="right">
              <span className="font-medium">{p.label}</span>
              <span className="ml-2 text-ink-faint">{p.note}</span>
            </TooltipContent>
          </Tooltip>
        );
      })}

      <span className="flex-1" />

      {(Object.keys(PANE_ICON) as PaneId[]).map((id) => {
        const Icon = PANE_ICON[id];
        return (
          <Item
            key={id}
            label={`${PANE_LABEL[id]} 접기/펼치기`}
            hint={PANE_KEY[id]}
            active={!collapsed[id]}
            aria-pressed={!collapsed[id]}
            onClick={() => togglePane(id)}
          >
            <Icon className={cn("size-[18px]", collapsed[id] && "opacity-45")} />
          </Item>
        );
      })}

      <Item
        label="테마 전환"
        onClick={() => setTheme(document.documentElement.dataset.theme === "light" ? "dark" : "light")}
      >
        <Contrast className="size-[18px]" />
      </Item>
    </nav>
  );
}
