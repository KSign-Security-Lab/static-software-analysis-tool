"use client";

import { Boxes } from "lucide-react";
import { useMemo } from "react";

import { EmptyState } from "@/components/workbench/PanelShell";
import { fromAgent } from "@/lib/model/finding";
import { useFindings } from "@/lib/run/queries";
import { useOpenFile, useRevealLine, useSelection } from "@/lib/run/selection";
import { useGraphShape, useThreads } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { labelOf } from "@/lib/trace/process";
import { unitsOf } from "@/lib/trace/process";
import { cn } from "@/lib/utils";

/**
 * What the run actually looked at, one unit at a time.
 *
 * A unit is a chunk -- a symbol in a file -- and it is the atom this whole
 * pipeline works in: the funnel counts units, spans are named after them
 * (`triage:handle`, `lens:memory:handle`), and a finding comes from one. The
 * surface has never listed them, so "did it read the function I care about"
 * was a question with no answer short of reading the trace.
 *
 * It is also the answer to scale. Measured at roughly two units and thirty-one
 * spans per file, a hundred-file run is about two hundred units and three
 * thousand spans -- so the trace can never be a flat list, but a list of units
 * you open is exactly the right size. The 문제 list stays short however big the
 * run gets; this is the one that grows with it.
 *
 * Each row says what happened to that unit -- how many calls it took, what it
 * cost, and whether it produced anything -- which is the per-unit form of the
 * coverage meter in the right column.
 */
export default function Units() {
  const [runId] = useRunId();
  const threads = useThreads(runId);
  const shape = useGraphShape();
  const findings = useFindings(runId);
  const { select } = useSelection();
  const [, setPath] = useOpenFile();
  const [, setLine] = useRevealLine();

  const units = useMemo(
    () => unitsOf(threads.data?.threads ?? [], shape.data?.steps ?? []),
    [threads.data, shape.data],
  );

  // Which units produced a claim. `chunkIds` is on the finding because one
  // claim can be raised from several units after merging.
  const raised = useMemo(() => {
    const map = new Map<string, number>();
    for (const finding of fromAgent(findings.data?.findings ?? [])) {
      for (const chunk of finding.chunkIds) map.set(chunk, (map.get(chunk) ?? 0) + 1);
    }
    return map;
  }, [findings.data]);

  if (units.length === 0) {
    return (
      <EmptyState icon={Boxes} title="아직 읽은 단위가 없습니다">
        검사를 실행하면 이 코드가 함수 단위로 쪼개져 하나씩 읽힙니다. 그 목록이 여기 나옵니다.
      </EmptyState>
    );
  }

  return (
    <ul className="py-1">
      {units.map((unit) => {
        const found = raised.get(unit.id) ?? 0;
        // What the unit's last step concluded, in the reader's language. The
        // step ids are the agent's own everywhere they identify something; this
        // is one of the two places they are narrated.
        const last = unit.exchanges[unit.exchanges.length - 1];

        return (
          <li key={unit.id}>
            <button
              type="button"
              onClick={() => {
                if (!unit.file) return;
                void setPath(unit.file);
                void setLine(null);
                select(null);
              }}
              className="flex w-full items-start gap-2 border-l-2 border-l-transparent px-2 py-1.5 text-left transition-colors hover:bg-surface-2"
            >
              <span
                className={cn(
                  "mt-1 size-1.5 shrink-0 rounded-full",
                  found > 0 ? "bg-danger" : unit.exchanges.length > 0 ? "bg-line-3" : "bg-line-2",
                )}
                aria-hidden
              />
              <span className="min-w-0 flex-1">
                <span className="flex items-baseline gap-1.5">
                  <span className="min-w-0 truncate font-mono text-xs text-ink">{unit.symbol ?? unit.id}</span>
                  {found > 0 && <span className="shrink-0 text-2xs text-danger">문제 {found}</span>}
                </span>
                <span className="flex items-baseline gap-1.5 pt-0.5">
                  {unit.file && <span className="min-w-0 truncate font-mono text-2xs text-ink-faint">{unit.file}</span>}
                  <span className="shrink-0 font-mono text-2xs text-ink-faint">
                    호출 {unit.exchanges.length}
                    {unit.tokens > 0 ? ` · ${unit.tokens.toLocaleString()} tok` : ""}
                  </span>
                </span>
                {last && <span className="block truncate text-2xs text-ink-faint">{labelOf(last)}까지</span>}
              </span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
