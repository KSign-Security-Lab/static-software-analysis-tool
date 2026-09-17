import { ShieldCheck, ShieldQuestion } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { STANDING_LABEL, type Standing } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

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
