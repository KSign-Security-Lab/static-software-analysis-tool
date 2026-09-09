import { CircleSlash, HelpCircle, TestTube } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { LIVENESS_LABEL, type Liveness } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

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
