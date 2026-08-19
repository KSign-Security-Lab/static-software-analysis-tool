"use client";

import { ExternalLink, MousePointerSquareDashed } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import { useDataset, useDatasetId, useInstanceId } from "@/lib/bench/queries";
import { OUTCOME_DOT, OUTCOME_LABEL } from "@/lib/bench/types";
import { cn } from "@/lib/utils";

/**
 * One instance: where it broke, under what, and the way into the run.
 *
 * 검사에서 열기 is the reason this is a workbench surface rather than a static
 * report. A failure you cannot open is a number you cannot act on -- the whole
 * trace is already recorded, and this is one link away from it.
 *
 * The link is built here by hand. `hrefFor`/`carries` in perspectives.ts is the
 * rail's mechanism: it copies params off the *current* URL into the target's
 * declared list, and this surface's URL never holds `run=`. Reaching for it
 * would produce a link to 검사 with no run on it.
 */
export default function InstanceDetail() {
  const [datasetId] = useDatasetId();
  const [instanceId] = useInstanceId();
  const view = useDataset(datasetId);

  const instance = view.data?.instances.find((i) => i.id === instanceId);

  if (!instance) {
    return (
      <PanelShell title="상세">
        <EmptyState icon={MousePointerSquareDashed} title="인스턴스를 고르세요">
          왼쪽 목록에서 하나를 고르면 어디서 어떻게 끊겼는지, 어떤 설정으로 돌린 것인지가 여기 나옵니다.
        </EmptyState>
      </PanelShell>
    );
  }

  return (
    <PanelShell title={<span className="font-mono text-xs">{instance.id}</span>}>
      <div className="flex flex-col gap-4 p-3">
        <div>
          <p className="flex items-center gap-1.5 text-sm text-ink-strong">
            <span className={cn("size-2 rounded-full", OUTCOME_DOT[instance.outcome])} aria-hidden />
            {OUTCOME_LABEL[instance.outcome]}
          </p>
          {instance.note && <p className="pt-1.5 text-xs leading-relaxed text-ink-muted">{instance.note}</p>}
        </div>

        {instance.contaminated && (
          <div className="rounded-md border border-warn/40 bg-warn-wash/40 p-2.5">
            <p className="text-2xs font-medium text-warn">오염됨 — 채점에서 제외</p>
            <p className="pt-1 text-2xs leading-relaxed text-ink-muted">
              {instance.contamination_reason || "이유가 기록되어 있지 않습니다."}
            </p>
            <p className="pt-1 text-2xs text-ink-faint">목록에는 그대로 남습니다. 무엇을 왜 뺐는지도 결과입니다.</p>
          </div>
        )}

        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-2xs">
          {instance.cwe && (
            <>
              <dt className="text-ink-faint">CWE</dt>
              <dd className="font-mono text-ink-muted">{instance.cwe}</dd>
            </>
          )}
          {instance.cve && (
            <>
              <dt className="text-ink-faint">CVE</dt>
              <dd className="font-mono text-ink-muted">{instance.cve}</dd>
            </>
          )}
          <dt className="text-ink-faint">설정</dt>
          <dd className="truncate font-mono text-ink-muted">{instance.config_hash ?? "기록 없음"}</dd>
        </dl>

        {instance.run_id ? (
          <Button asChild size="sm" variant="outline">
            <Link href={`/agent?run=${encodeURIComponent(instance.run_id)}`}>
              <ExternalLink />
              검사에서 열기
            </Link>
          </Button>
        ) : (
          <p className="text-2xs text-ink-faint">
            이 인스턴스를 돌린 검사가 없습니다. 돌리고 나면 여기서 그 검사를 그대로 열 수 있습니다.
          </p>
        )}
      </div>
    </PanelShell>
  );
}
