"use client";

import { Check, Wrench } from "lucide-react";
import { useMemo } from "react";

import DiffView from "@/components/editor/DiffView.lazy";
import { Button } from "@/components/ui/button";
import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import { wireId, type UiFinding } from "@/lib/model/finding";
import { useApplyFix, useFile, useProposeFix } from "@/lib/run/queries";
import { phaseFor } from "@/lib/run/reduce";
import { useRun } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";

/**
 * The patch, side by side.
 *
 * It was a unified diff inside a 400px column, where 396 characters of C wrap
 * into nine ragged lines and a `-` and a `+` on the same statement end up four
 * rows apart. A diff is a comparison and a comparison wants two columns; the
 * centre has 880px and `DiffView` was already built -- it had been used only to
 * compare a replayed prompt against its original.
 */
export default function FixView({ finding }: { finding: UiFinding | null }) {
  const [runId] = useRunId();
  const { phase: streamed } = useRunStream();
  const run = useRun(runId);
  const file = useFile(runId, finding?.primary.file ?? null);
  const apply = useApplyFix(runId);
  const propose = useProposeFix(runId);

  const phase = phaseFor(streamed, run.data?.status);
  // Never while a run is in flight: the inspection is reading these files.
  const running = phase === "running" || phase === "starting";

  const original = file.data?.content ?? "";

  /**
   * The file as it would be, not the fragment on its own.
   *
   * `replacement` is the new text for the claim's line range, so handing it to
   * a diff against the whole file marks every other line as deleted -- which is
   * what shipped: thirteen red lines and six green ones for a two-line change.
   * Splicing it in first is the same thing `POST .../apply` does on the server,
   * and doing it here is what makes this a preview of that.
   */
  const modified = useMemo(() => {
    if (!finding?.replacement || !original) return null;
    const lines = original.split("\n");
    const from = Math.max(0, finding.primary.startLine - 1);
    const to = Math.max(from, finding.primary.endLine || finding.primary.startLine);
    return [...lines.slice(0, from), ...finding.replacement.split("\n"), ...lines.slice(to)].join("\n");
  }, [original, finding]);

  if (!finding) {
    return (
      <PanelShell>
        <EmptyState icon={Wrench} title="고칠 문제를 먼저 고르세요">
          왼쪽 ‘문제’ 에서 하나를 고르면, 에이전트가 제안한 수정을 원래 코드와 나란히 놓고 봅니다.
        </EmptyState>
      </PanelShell>
    );
  }

  return (
    <PanelShell
      title={<span className="font-mono text-xs">{finding.primary.file}</span>}
      actions={
        modified ? (
          <Button
            size="sm"
            disabled={!runId || running || apply.isPending}
            onClick={() => apply.mutate(wireId(finding.id))}
          >
            <Check />
            {apply.isPending ? "적용 중…" : "이대로 고치기"}
          </Button>
        ) : (
          <Button
            size="sm"
            variant="outline"
            disabled={!runId || running || propose.isPending}
            onClick={() => propose.mutate(wireId(finding.id))}
          >
            <Wrench />
            {propose.isPending ? "만드는 중…" : "고칠 코드 만들기"}
          </Button>
        )
      }
      bodyClassName="flex flex-col overflow-hidden"
    >
      {/* The prose, above the code it describes. `UiFinding` flattens the
          wire's summary and detail into one string -- see lib/model/finding. */}
      {finding.remediation && (
        <p className="shrink-0 border-b border-line px-3 py-2 whitespace-pre-line text-xs leading-relaxed text-ink-muted">
          {finding.remediation}
        </p>
      )}

      {modified ? (
        // `absolute inset-0` inside a `relative` box, because `DiffView` sizes
        // itself `h-full` -- a percentage of a parent that, being `flex-1`, has
        // no definite height for it to be a percentage of. Left alone the diff
        // collapsed to a two-pixel sliver with one red line showing. Same shape
        // as the React Flow `#004` bug, same fix: take the size from a
        // positioned ancestor rather than asking for a share of nothing.
        <div className="relative min-h-0 flex-1">
          <div className="absolute inset-0">
            <DiffView original={original} modified={modified} language={file.data?.language} />
          </div>
        </div>
      ) : (
        <EmptyState icon={Wrench} title="아직 고칠 코드가 없습니다">
          이 판단에는 패치가 딸려 오지 않았습니다. 위 ‘고칠 코드 만들기’ 를 누르면 에이전트가 하나 써 봅니다.
        </EmptyState>
      )}
    </PanelShell>
  );
}
