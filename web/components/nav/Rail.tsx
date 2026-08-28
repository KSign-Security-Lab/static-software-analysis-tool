"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import type { ReactNode } from "react";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";
import { PERSPECTIVES, hrefFor, perspectiveFor } from "@/lib/workbench/perspectives";

/**
 * The 64px rail of surfaces, shared by the two shells.
 *
 * 검사 has its own shell and the four research surfaces share the workbench, so
 * the rail is the one thing genuinely common to both -- and it has to be, or the
 * two shells would drift into two different navigations for one application.
 *
 * Named, not only drawn. Five glyphs and a tooltip is a navigation you can use
 * once you already know it, and these are quite different tools sharing one
 * application -- an icon cannot say which inspects code and which reads a
 * benchmark. The tooltip keeps the sentence that will not fit.
 *
 * Fixed width and a flex sibling of whatever it sits beside, never a panel: the
 * workbench sizes its panels in percentages, so a rail expressed as one would
 * breathe with the window.
 */
export default function Rail({
  wordmark = false,
  foot,
}: {
  /** Shown only where no title bar carries it, which is 검사. */
  wordmark?: boolean;
  /** Controls belonging to no surface in particular. The shell decides. */
  foot?: ReactNode;
}) {
  const pathname = usePathname();
  const params = useSearchParams();
  const current = perspectiveFor(pathname);

  return (
    <nav
      aria-label="화면"
      className="flex w-16 shrink-0 flex-col items-center gap-px border-r border-line bg-surface py-1"
    >
      {wordmark && (
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

      {/* `mt-auto` rather than a spacer div, so the foot sits against the floor
          at every window height without reserving anything. */}
      {foot && <div className="mt-auto flex w-full flex-col items-center gap-0.5 pt-2">{foot}</div>}
    </nav>
  );
}

/**
 * How to use the surface you are on, in order.
 *
 * Read out of `perspectives.ts` rather than written here, because that file is
 * where each surface's purpose and steps are declared and two copies of a
 * walkthrough is one copy that goes stale.
 */
export function HowToUse() {
  const current = perspectiveFor(usePathname());
  if (!current) return null;

  return (
    <>
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
    </>
  );
}
