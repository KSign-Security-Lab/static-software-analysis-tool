"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { PERSPECTIVES, hrefFor, perspectiveFor } from "@/lib/workbench/perspectives";

/**
 * The 64px rail: the five perspectives, and nothing else.
 *
 * Named, not only drawn. Five glyphs and a tooltip is a navigation you can use
 * once you already know it, and these are five quite different tools sharing
 * one shell -- an icon cannot say which inspects code and which reads a
 * finished run's reasoning. The tooltip keeps the sentence that will not fit.
 *
 * The panel folds and the theme used to sit at the foot of this rail. They are
 * window controls rather than places to go, so they moved to the title bar,
 * which leaves this doing one job.
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

  return (
    <nav aria-label="화면" className="flex w-16 shrink-0 flex-col items-center gap-px border-r border-line bg-surface py-1">
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
    </nav>
  );
}
