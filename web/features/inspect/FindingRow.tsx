"use client";

import { Checkbox } from "@/components/ui/checkbox";
import { Verdict } from "@/components/panel/verdict";
import { isFixable } from "@/lib/inspect/filter";
import { SEVERITY_DOT, SEVERITY_LABEL, standingOf, type UiFinding } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

/**
 * One finding, as a row.
 *
 * Shared by the live list during a scan and the table afterwards, because they
 * are the same rows -- a reader who started reading at thirty seconds should not
 * have to re-learn the layout when the scan ends. The tick is what differs, and
 * it is a prop rather than a branch on the stage.
 *
 * The severity dot carries the alarm and nothing else competes with it: the
 * standing badge is deliberately uncoloured (see `components/panel/verdict`),
 * because two marks both trying to say how worried to be is how a list stops
 * being scannable.
 */
export default function FindingRow({
  finding,
  selected = false,
  ticked,
  onTick,
  onOpen,
}: {
  finding: UiFinding;
  selected?: boolean;
  /** Omit to render a row that cannot be put in the bucket. */
  ticked?: boolean;
  onTick?: () => void;
  onOpen?: () => void;
}) {
  const standing = standingOf(finding);

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
            // A finding with only advice can still be ticked: the dialog offers
            // to make code for it. Refusing the tick would hide that door.
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
          {/* Says nothing when there is a patch, because that is the expected
              case and a badge on every row is a badge nobody reads. */}
          {!isFixable(finding) && <span className="shrink-0 text-warn">패치 없음</span>}
          {finding.chunkIds.length > 1 && <span className="shrink-0">{finding.chunkIds.length}회 보고</span>}
        </span>
      </button>

      {standing && <Verdict standing={standing} confidence={finding.confidence} className="mt-px shrink-0" />}
    </div>
  );
}
