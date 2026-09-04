import { CircleSlash, HelpCircle, TestTube } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { LIVENESS_LABEL, type Liveness } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

/**
 * Whether the code a finding sits in runs.
 *
 * The second axis, and the reason it exists: a reader told us a real defect in a
 * never-called helper is not the same news as one in a request handler, and the
 * report gave them nothing to tell those apart with.
 *
 * Quiet, for the reason `verdict.tsx` is quiet -- the severity dot is the one
 * mark allowed to say how alarmed to be, and a second coloured badge competing
 * with it is how a list stops being scannable.
 *
 * Silent on `live` and on `unreferenced`. `live` is the ordinary case and a
 * badge on every row is a badge nobody reads; `unreferenced` is genuinely
 * common -- most scans are one directory of a program rather than the program --
 * so marking it would put a badge on half the list and say almost nothing. The
 * three that remain are the ones that change what a reader does next.
 *
 * `why` is the tooltip, so the label can be checked rather than trusted. That
 * matters more here than for a verdict: this one is derived from a call graph
 * with known blind spots, and it says so out loud.
 */
const ICON: Partial<Record<Liveness, typeof CircleSlash>> = {
  unreachable: CircleSlash,
  excluded: TestTube,
  unknown: HelpCircle,
};

export function LivenessBadge({
  liveness,
  why = [],
  className,
}: {
  liveness: Liveness;
  why?: string[];
  className?: string;
}) {
  const Icon = ICON[liveness];
  if (!Icon) return null;

  return (
    <Badge
      variant="outline"
      className={cn("gap-1 font-normal text-ink-muted", className)}
      title={why.length ? why.join(" · ") : undefined}
    >
      <Icon className="size-3 shrink-0 text-ink-faint" aria-hidden />
      {LIVENESS_LABEL[liveness]}
    </Badge>
  );
}
