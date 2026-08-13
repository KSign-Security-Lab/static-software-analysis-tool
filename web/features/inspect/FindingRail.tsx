"use client";

import { ShieldCheck } from "lucide-react";
import { useMemo } from "react";

import { Verdict } from "@/components/panel/verdict";
import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import {
  SEVERITY_DOT,
  SEVERITY_LABEL,
  fromAgent,
  sortFindings,
  standingOf,
  type UiFinding,
} from "@/lib/model/finding";
import { useDiff, useFindings } from "@/lib/run/queries";
import { useCompareRun, useOpenFile, useRevealLine, useSelectedFinding } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * The problems, as the thing this side of the screen is for.
 *
 * They were in a shelf along the bottom, which is where an application puts its
 * console -- the place output accumulates while you work on something else. They
 * are not output. They are the answer, and everything else on screen exists to
 * explain or repair one of them, so they get the rail and the rail gets nothing
 * else to compete with.
 *
 * A row is the whole of what a reader needs to choose between problems: how bad,
 * what kind, where, and whether anybody checked. Clicking one drives the editor
 * and the panel underneath it; nothing here opens in place, because a list that
 * expands is a list you lose your position in.
 */
export default function FindingRail() {
  const [runId] = useRunId();
  const [findingId, setFindingId] = useSelectedFinding();
  const [, setPath] = useOpenFile();
  const [, setLine] = useRevealLine();
  const [against] = useCompareRun();
  const { phase } = useRunStream();

  const findings = useFindings(runId);
  const diff = useDiff(runId, against);

  const rows = useMemo(() => sortFindings(fromAgent(findings.data?.findings ?? [])), [findings.data]);
  // Both sides through `fromAgent`, because the rows these mark carry the view
  // model's prefixed ids and the wire's are bare.
  const marks = useMemo(() => {
    if (!diff.data) return null;
    return {
      fresh: new Set(fromAgent(diff.data.new).map((each) => each.id)),
      fixed: fromAgent(diff.data.fixed).length,
    };
  }, [diff.data]);

  const running = phase === "running" || phase === "starting";
  const survived = rows.filter((each) => each.verified !== false).length;

  return (
    <PanelShell
      title="문제"
      note={
        rows.length > 0
          ? [`${rows.length}건`, marks && marks.fixed > 0 ? `고침 ${marks.fixed}` : null]
              .filter(Boolean)
              .join(" · ")
          : undefined
      }
    >
      {rows.length === 0 ? (
        <EmptyState icon={ShieldCheck} title={running ? "검사 중입니다" : "아직 결과가 없습니다"}>
          {running
            ? "문제를 찾는 대로 여기에 하나씩 올라옵니다."
            : "가운데에 코드를 넣고 ‘검사 실행’을 누르세요."}
        </EmptyState>
      ) : (
        <ul>
          {rows.map((finding) => {
            const open = finding.id === findingId;
            return (
              <li key={finding.id}>
                <button
                  type="button"
                  onClick={() => {
                    void setFindingId(finding.id);
                    // One click puts the code on screen at the line. Choosing a
                    // problem and then having to go and find it is the step this
                    // rail exists to remove.
                    void setPath(finding.primary.file);
                    void setLine(finding.primary.startLine);
                  }}
                  className={cn(
                    "flex w-full items-start gap-2 border-l-2 px-2.5 py-2 text-left transition-colors",
                    open
                      ? "border-l-accent bg-accent-wash"
                      : "border-l-transparent hover:bg-surface-2",
                  )}
                >
                  <span
                    aria-label={SEVERITY_LABEL[finding.severity]}
                    className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", SEVERITY_DOT[finding.severity])}
                  />
                  <span className="min-w-0 flex-1 space-y-1">
                    <span className="block text-xs leading-snug font-medium text-ink-strong">
                      {finding.title}
                    </span>
                    <span className="flex flex-wrap items-center gap-x-2 gap-y-1 text-2xs text-ink-faint">
                      {finding.cwe && <span className="font-mono">{finding.cwe}</span>}
                      <span className="font-mono">
                        {finding.primary.file}:{finding.primary.startLine}
                      </span>
                      {marks?.fresh.has(finding.id) && <span className="text-accent-ink">새로</span>}
                    </span>
                    <Standing finding={finding} />
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {rows.length > 0 && survived < rows.length && (
        <p className="border-t border-line px-2.5 py-1.5 text-2xs text-ink-faint">
          {rows.length - survived}건은 검증 한도를 넘겨 확인하지 못했습니다.
        </p>
      )}
    </PanelShell>
  );
}

/** Nothing at all for an engine with no verification step. */
function Standing({ finding }: { finding: UiFinding }) {
  const standing = standingOf(finding);
  if (!standing) return null;
  return <Verdict standing={standing} confidence={finding.confidence ?? undefined} className="mt-0.5" />;
}
