"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { LivenessBadge } from "@/components/panel/liveness";
import { Verdict } from "@/components/panel/verdict";
import { isFixable } from "@/lib/inspect/filter";
import { SEVERITY_DOT, SEVERITY_LABEL, livenessOf, standingOf, type UiFinding } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

export default function FindingRow({
  finding,
  selected = false,
  ticked,
  onTick,
  onOpen,
}: {
  finding: UiFinding;
  selected?: boolean;
  ticked?: boolean;
  onTick?: () => void;
  onOpen?: () => void;
}) {
  const standing = standingOf(finding);
  const liveness = livenessOf(finding);

  return (
    <div
      className={cn(
        "flex w-full items-start gap-2 px-2.5 py-2 transition-colors",
        onOpen && "cursor-pointer hover:bg-surface-2",
        selected && "bg-surface-2",
      )}
    >
      {ticked !== undefined && (
        <span className="pt-0.5" onClick={(event) => event.stopPropagation()}>
          <Checkbox
            checked={ticked}
            onCheckedChange={onTick}
            aria-label={`${finding.title} 담기`}
          />
        </span>
      )}

      <button
        type="button"
        onClick={onOpen}
        disabled={!onOpen}
        className="min-w-0 flex-1 text-left disabled:cursor-default"
      >
        <span className="flex items-baseline gap-1.5">
          <span
            className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", SEVERITY_DOT[finding.severity])}
            aria-hidden
          />
          <span className="sr-only">{SEVERITY_LABEL[finding.severity]}</span>
          <span className={cn("min-w-0 flex-1 truncate text-xs", selected ? "text-ink-strong" : "text-ink")}>
            {finding.title}
          </span>
          {finding.cwe && <span className="shrink-0 font-mono text-2xs text-ink-muted">{finding.cwe}</span>}
        </span>
        <span className="mt-0.5 flex items-baseline gap-2 pl-3 font-mono text-2xs text-ink-faint">
          <span className="min-w-0 truncate">
            {finding.primary.file}:{finding.primary.startLine}
          </span>
          {!isFixable(finding) && <span className="shrink-0 text-warn">패치 없음</span>}
          {finding.chunkIds.length > 1 && <span className="shrink-0">{finding.chunkIds.length}회 보고</span>}
        </span>
      </button>

      {liveness && (
        <LivenessBadge liveness={liveness} why={finding.reach?.why ?? []} className="mt-px shrink-0" />
      )}
      {standing && <Verdict standing={standing} confidence={finding.confidence} className="mt-px shrink-0" />}
    </div>
  );
}
