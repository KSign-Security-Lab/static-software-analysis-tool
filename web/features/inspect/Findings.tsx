"use client";

import { ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/workbench/PanelShell";
import BucketTray from "@/features/inspect/BucketTray";
import FilterBar from "@/features/inspect/FilterBar";
import FindingDetail from "@/features/inspect/FindingDetail";
import FindingRow from "@/features/inspect/FindingRow";
import { NO_FACETS, apply, sort, type Facets } from "@/lib/inspect/filter";
import { setMany, toggle, useBucket } from "@/lib/inspect/bucket";
import { type UiFinding } from "@/lib/model/finding";
import { useSort } from "@/lib/run/selection";
import { useOpenFinding } from "@/lib/run/queries";
import { useRunId } from "@/lib/run/use-run-id";
import { useSelection } from "@/lib/run/selection";

/**
 * The report, and one finding open beside it.
 *
 * Two columns, because that is the shape of the work: decide about a list while
 * reading one of its rows. The old surface spent four panes on this and still
 * could not do it -- reading a finding's reasoning meant opening a tab over the
 * code the reasoning was about.
 *
 * The list is the left column and it stays put. Every previous version made the
 * centre the widest region because an editor lived there; nothing does now, and
 * the two things that actually want width are a finding's evidence and its
 * patch, which are both in the detail column.
 */
export default function Findings({ findings }: { findings: UiFinding[] }) {
  const [runId] = useRunId();
  const [order] = useSort();
  const { select } = useSelection();
  const open = useOpenFinding(runId);
  const ticked = useBucket(runId);
  const [facets, setFacets] = useState<Facets>(NO_FACETS);

  const shown = useMemo(() => sort(apply(findings, facets), order), [findings, facets, order]);
  const tickedSet = useMemo(() => new Set(ticked), [ticked]);

  if (findings.length === 0) {
    return (
      <div className="min-h-0 flex-1 overflow-auto">
        <div className="mx-auto w-full max-w-2xl px-6 py-10">
          <EmptyState icon={ShieldCheck} title="찾은 취약점이 없습니다">
            읽은 단위에서 보고할 것이 없었습니다. 그것도 결과입니다 — 무엇을 얼마나 읽었는지는 ‘지난 검사’ 에
            남아 있습니다.
          </EmptyState>
        </div>
      </div>
    );
  }

  return (
    <div className="grid min-h-0 flex-1 grid-cols-[minmax(0,1fr)_minmax(0,26rem)] xl:grid-cols-[minmax(0,1fr)_minmax(0,34rem)]">
      <section className="flex min-h-0 min-w-0 flex-col border-r border-line">
        <FilterBar
          findings={findings}
          shown={shown}
          facets={facets}
          onFacets={setFacets}
          onTickAll={(on) =>
            runId &&
            setMany(
              runId,
              shown.map((each) => each.id),
              on,
            )
          }
          allTicked={shown.length > 0 && shown.every((each) => tickedSet.has(each.id))}
        />

        <ul className="min-h-0 flex-1 divide-y divide-line overflow-auto">
          {shown.map((finding) => (
            <li key={finding.id}>
              <FindingRow
                finding={finding}
                selected={open?.id === finding.id}
                ticked={tickedSet.has(finding.id)}
                onTick={() => runId && toggle(runId, finding.id)}
                onOpen={() => select({ kind: "finding", id: finding.id })}
              />
            </li>
          ))}
          {shown.length === 0 && (
            <li className="px-3 py-6 text-xs text-ink-faint">
              이 조건에 맞는 것이 없습니다. 위에서 조건을 지우면 다시 보입니다.
            </li>
          )}
        </ul>

        <BucketTray findings={findings} />
      </section>

      <FindingDetail finding={open} />
    </div>
  );
}
