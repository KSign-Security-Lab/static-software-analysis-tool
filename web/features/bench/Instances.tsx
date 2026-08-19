"use client";

import { FlaskConical } from "lucide-react";
import { useMemo } from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { EmptyState } from "@/components/workbench/PanelShell";
import { useDataset, useDatasetId, useInstanceId } from "@/lib/bench/queries";
import { useDatasets } from "@/lib/bench/queries";
import { setMany, toggle, useSelection } from "@/lib/bench/selection";
import { OUTCOME_DOT, groupByOutcome } from "@/lib/bench/types";
import { cn } from "@/lib/utils";

/**
 * What the sweep looked at, grouped by where it broke.
 *
 * By failure stage and not by score, and that ordering is the argument. A page
 * that leads with the number turns every conversation into the number; a page
 * that leads with 위치 못 찾음 · 찾고 오독 · 오탐 says which of those to work on
 * next, which is the only thing a benchmark is actually good for.
 *
 * The same shape as 검사's 문제 list -- sticky group header, dot, mono tag,
 * truncated line -- because it is the same problem with different columns.
 */
export default function Instances() {
  const [datasetId, setDatasetId] = useDatasetId();
  const [instanceId, setInstanceId] = useInstanceId();
  const catalogue = useDatasets();
  const view = useDataset(datasetId);

  const grouped = useMemo(
    () => (view.data ? groupByOutcome(view.data.instances, view.data.dataset.stages) : []),
    [view.data],
  );

  const datasets = catalogue.data?.datasets ?? [];
  const chosen = useSelection(datasetId);
  const ticked = useMemo(() => new Set(chosen), [chosen]);
  // Only the sets that have a sweep to run. Ticking a corpus file would offer
  // to run something there is no runner for.
  const selectable = Boolean(view.data?.dataset.split);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* The selector, and the kind said out loud beside it. Two datasets that
          are never comparable should not look like two tabs of one thing. */}
      <div className="shrink-0 border-b border-line px-2 py-1.5">
        <div className="flex flex-wrap gap-1">
          {datasets.map((dataset) => {
            const current = dataset.id === datasetId;
            return (
              <button
                key={dataset.id}
                type="button"
                onClick={() => void setDatasetId(dataset.id)}
                className={cn(
                  "rounded px-2 py-1 text-2xs transition-colors",
                  current ? "bg-accent text-accent-fg" : "text-ink-muted hover:bg-surface-2",
                )}
              >
                {dataset.label}
                <span className={cn("ml-1", current ? "opacity-80" : "text-ink-faint")}>
                  {dataset.kind === "held_out" ? "고정" : "내부"}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {/* Genuinely no rows -- the dataset has not been fetched. A split that
            has been fetched but not run is a list of 안 돌림, and that list is
            the thing you tick to choose what to run, so it must not be replaced
            by a paragraph. */}
        {view.data && view.data.instances.length === 0 ? (
          <EmptyState icon={FlaskConical} title="아직 결과가 없습니다">
            {view.data.dataset.how_to_run}
          </EmptyState>
        ) : (
          <ul className="py-1">
            {grouped.map((group) => (
              <li key={group.outcome}>
                <p className="sticky top-0 z-10 flex items-center gap-1.5 bg-surface-2 px-2.5 py-1 text-2xs text-ink-muted">
                  {/* 196 rows is not a thing anyone ticks one at a time. */}
                  {selectable && (
                    <Checkbox
                      checked={group.items.every((i) => ticked.has(i.id))}
                      onCheckedChange={(value) =>
                        setMany(
                          datasetId,
                          group.items.map((i) => i.id),
                          value === true,
                        )
                      }
                      aria-label={`${group.label} 전체 선택`}
                    />
                  )}
                  <span className={cn("size-1.5 rounded-full", OUTCOME_DOT[group.outcome])} aria-hidden />
                  {group.label}
                  <span className="font-mono text-ink-faint">{group.items.length}</span>
                </p>
                <ul>
                  {group.items.map((instance) => {
                    const current = instance.id === instanceId;
                    return (
                      <li
                        key={instance.id}
                        className={cn(
                          "flex items-start border-l-2 transition-colors",
                          current ? "border-l-accent bg-surface-2" : "border-l-transparent hover:bg-surface-2",
                        )}
                      >
                        {/* Beside the row rather than inside it: a checkbox
                            nested in a button is not a thing a browser can
                            resolve a click on. */}
                        {selectable && (
                          <span className="flex shrink-0 items-center py-1.5 pl-2">
                            <Checkbox
                              checked={ticked.has(instance.id)}
                              onCheckedChange={() => toggle(datasetId, instance.id)}
                              aria-label={`${instance.id} 선택`}
                            />
                          </span>
                        )}
                        <button
                          type="button"
                          onClick={() => void setInstanceId(instance.id)}
                          className="flex min-w-0 flex-1 items-start gap-2 px-2 py-1.5 text-left"
                        >
                          <span className="min-w-0 flex-1">
                            <span className="flex items-baseline gap-1.5">
                              {/* The filename, not the path. Every row in a CWE
                                  folder shares a 34-character prefix that
                                  truncated the only part that differed, and the
                                  folder is already said by the CWE tag below. */}
                              <span
                                className={cn(
                                  "min-w-0 truncate font-mono text-xs",
                                  current ? "font-medium text-ink-strong" : "text-ink",
                                )}
                              >
                                {instance.id.split("/").pop()}
                              </span>
                              {/* Marked, never filtered. What was dropped and
                                  why is part of the result. */}
                              {instance.contaminated && (
                                <span className="shrink-0 rounded bg-warn-wash px-1 text-2xs text-warn">오염됨</span>
                              )}
                            </span>
                            <span className="flex items-baseline gap-1.5 pt-0.5">
                              {instance.cwe && (
                                <span className="shrink-0 font-mono text-2xs text-ink-faint">{instance.cwe}</span>
                              )}
                              <span className="min-w-0 truncate text-2xs text-ink-faint">{instance.note}</span>
                            </span>
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
