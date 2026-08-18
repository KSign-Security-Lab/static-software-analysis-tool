"use client";

import { ShieldCheck } from "lucide-react";
import { useMemo } from "react";

import { Verdict } from "@/components/panel/verdict";
import { EmptyState } from "@/components/workbench/PanelShell";
import { SEVERITY_DOT, fromAgent, sortFindings, standingOf, type UiFinding } from "@/lib/model/finding";
import { useFindings } from "@/lib/run/queries";
import { useOpenFile, useRevealLine, useSelection } from "@/lib/run/selection";
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
  );
}
