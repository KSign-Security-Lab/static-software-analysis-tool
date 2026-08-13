import { ShieldCheck, ShieldQuestion } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { STANDING_LABEL, type Standing } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

/**
 * What verification made of a claim.
 *
 * One component because there were two, disagreeing. The finding list rendered a
 * surviving claim in `text-ok` and the run record rendered the same fact in
 * `text-danger` -- green and red, same word, same screen -- because each pane had
 * coined its own words and its own colour for it.
 *
 * Quiet on purpose. The severity dot beside it already says how bad the thing is;
 * this only has to say whether anybody checked. Colouring it as well meant two
 * marks competing to be the one that tells you how alarmed to be.
 */
export function Verdict({ standing, confidence, className }: { standing: Standing; confidence?: number; className?: string }) {
  const Icon = standing === "confirmed" ? ShieldCheck : ShieldQuestion;
  const sure = typeof confidence === "number" && confidence > 0 ? ` · ${Math.round(confidence * 100)}%` : "";

  return (
    <Badge variant="outline" className={cn("gap-1 font-normal text-ink-muted", className)}>
      <Icon className="size-3 shrink-0 text-ink-faint" aria-hidden />
      {STANDING_LABEL[standing]}
      {sure}
    </Badge>
  );
}
