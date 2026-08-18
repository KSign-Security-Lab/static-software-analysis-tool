"use client";

import { ShieldCheck, TriangleAlert } from "lucide-react";
import { useMemo } from "react";

import { Verdict } from "@/components/panel/verdict";
import { EmptyState } from "@/components/workbench/PanelShell";
import { SEVERITY_DOT, fromAgent, sortFindings, standingOf, type UiFinding } from "@/lib/model/finding";
import { useDiff, useFindings } from "@/lib/run/queries";
import { useCompareAgainst, useOpenFile, useRevealLine, useSelection } from "@/lib/run/selection";
import { useSpans } from "@/lib/run/trace-queries";
import { failuresByClaim } from "@/lib/trace/failures";
import { claimOf } from "@/lib/trace/process";
import { useRunId } from "@/lib/run/use-run-id";
import { cn } from "@/lib/utils";

/**
 * What the run found, in the column that lists the run.
 *
 * It was a shelf along the bottom of the window, interleaved with every tool
 * call the agent made and filtered by a three-way toggle -- which is where an
 * application puts its console, the place output accumulates while you work on
 * something else. These are not output. They are the answer, and everything
 * else on the surface exists to explain or repair one of them.
 *
 * Grouped by file and worst-first inside it, because triage is per-file: you
 * are deciding which file to open, and a list sorted purely by severity makes
 * that decision by scattering each file across it.
 *
 * The calls that used to share this list are not lost -- they are steps in a
 * finding's 판단 과정, which is the only context in which anyone wanted one.
 */
export default function Problems() {
  const [runId] = useRunId();
  const findings = useFindings(runId);
  const { selection, select } = useSelection();
  const [, setPath] = useOpenFile();
  const [, setLine] = useRevealLine();

  /**
   * What changed since the run being compared against, if one is.
   *
   * Set in the run selector -- comparing is picking a second run, so it belongs
   * where you pick the first. `fresh` is the ids this run raised that the other
   * did not; anything else in the report was already there.
   */
  const [against] = useCompareAgainst();
  const diff = useDiff(runId, against);
  const fresh = useMemo(
    () => (against && diff.data ? new Set(fromAgent(diff.data.new).map((each) => each.id)) : null),
    [against, diff.data],
  );
  // Gone. They are not in this run's report at all, so they cannot be rows in
  // the list above -- they get their own group, greyed, and are not selectable:
  // there is no code here to open and no argument to read.
  const gone = useMemo(
    () => (against && diff.data ? fromAgent(diff.data.fixed) : []),
    [against, diff.data],
  );

  // Which claims lost their verdict or their patch. `claimOf` rebuilds the
  // same `CWE file:line` subject the agent names its spans with, so the report
  // and the trace join without either side knowing about the other.
  const spans = useSpans(runId);
  const broken = useMemo(() => failuresByClaim(spans.data?.spans ?? []), [spans.data]);

  const byFile = useMemo(() => {
    const all = sortFindings(fromAgent(findings.data?.findings ?? []));
    const groups = new Map<string, UiFinding[]>();
    for (const each of all) {
      const file = each.primary.file;
      groups.set(file, [...(groups.get(file) ?? []), each]);
    }
    return [...groups.entries()];
  }, [findings.data]);

  if (byFile.length === 0) {
    return (
      <EmptyState icon={ShieldCheck} title="아직 찾은 문제가 없습니다">
        위 ‘검사 실행’을 누르면 여기에 쌓입니다. 이미 검사했다면, 이 코드에서는 아무것도 찾지 못한 것입니다.
      </EmptyState>
    );
  }

  const open = selection?.kind === "finding" ? selection.id : null;

  return (
    <ul className="py-1">
      {byFile.map(([file, mine]) => (
        <li key={file}>
          <p className="sticky top-0 z-10 bg-surface-2 px-2.5 py-1 font-mono text-2xs text-ink-muted">{file}</p>
          <ul>
            {mine.map((finding) => {
              const standing = standingOf(finding);
              const current = finding.id === open || finding.mergedIds.includes(open ?? "");
              return (
                <li key={finding.id}>
                  <button
                    type="button"
                    onClick={() => {
                      select({ kind: "finding", id: finding.id });
                      // The claim's own line. An evidence step can move the
                      // editor somewhere else afterwards; this is where the
                      // finding is filed.
                      void setPath(finding.primary.file);
                      void setLine(finding.primary.startLine > 0 ? finding.primary.startLine : null);
                    }}
                    className={cn(
                      "flex w-full items-start gap-2 border-l-2 px-2 py-1.5 text-left transition-colors",
                      current
                        ? "border-l-accent bg-surface-2"
                        : "border-l-transparent hover:bg-surface-2",
                    )}
                  >
                    <span
                      className={cn("mt-1 size-1.5 shrink-0 rounded-full", SEVERITY_DOT[finding.severity])}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1">
                      <span
                        className={cn(
                          "block truncate text-xs",
                          current ? "font-medium text-ink-strong" : "text-ink",
                        )}
                      >
                        {finding.title}
                      </span>
                      <span className="flex items-center gap-1.5 pt-0.5">
                        {finding.cwe && <span className="font-mono text-2xs text-ink-faint">{finding.cwe}</span>}
                        <span className="font-mono text-2xs text-ink-faint">:{finding.primary.startLine}</span>
                        {standing && (
                          <Verdict standing={standing} confidence={finding.confidence ?? undefined} />
                        )}
                        {(broken.get(claimOf(finding)) ?? []).map((f) => (
                          <span
                            key={f.step}
                            className="flex items-center gap-1 text-2xs text-warn"
                            title={f.message}
                          >
                            <TriangleAlert className="size-3 shrink-0" />
                            {f.role} 실패
                          </span>
                        ))}
                        {fresh && (
                          <span className={cn("text-2xs", fresh.has(finding.id) ? "text-accent-ink" : "text-ink-faint")}>
                            {fresh.has(finding.id) ? "새로" : "그대로"}
                          </span>
                        )}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </li>
      ))}

      {gone.length > 0 && (
        <li>
          <p className="sticky top-0 z-10 bg-ok-wash/40 px-2.5 py-1 text-2xs text-ok">해결됨 {gone.length}</p>
          <ul>
            {gone.map((finding) => (
              <li
                key={finding.id}
                className="flex items-start gap-2 px-2 py-1.5 opacity-60"
                title="이 검사에는 없습니다. 비교 대상 검사에만 있었습니다."
              >
                <span className="mt-1 size-1.5 shrink-0 rounded-full bg-line-3" aria-hidden />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs text-ink-muted line-through">{finding.title}</span>
                  <span className="font-mono text-2xs text-ink-faint">
                    {finding.cwe} · {finding.primary.file}:{finding.primary.startLine}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </li>
      )}
    </ul>
  );
}
