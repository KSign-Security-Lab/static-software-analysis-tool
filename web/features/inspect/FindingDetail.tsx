"use client";

import { MousePointerClick, Wrench } from "lucide-react";
import { useMemo } from "react";

import { Disclosure } from "@/components/panel/disclosure";
import { Patch } from "@/components/panel/patch";
import { Verdict } from "@/components/panel/verdict";
import { Button } from "@/components/ui/button";
import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import { ROLE_LABEL, ROLE_TONE, fromAgent, standingOf, wireId, type UiFinding } from "@/lib/model/finding";
import { neighbours } from "@/lib/api/knowledge";
import { useKnowledge } from "@/lib/run/knowledge-queries";
import { useApplyFix, useFindings, useProposeFix } from "@/lib/run/queries";
import { useOpenFile, useRevealLine, useSelectedFinding } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import { useThreads } from "@/lib/run/trace-queries";
import { claimOf, labelOf, trailOf, unitsOf } from "@/lib/trace/process";
import { useGraphShape } from "@/lib/run/trace-queries";
import Link from "next/link";

/**
 * One problem, in full.
 *
 * The three questions a reader has about a finding, in the order they ask them:
 * why do you say that, how do I fix it, and -- only if they doubt the first two
 * -- how did you work it out. They were spread across a dock column, a second
 * pane and a tab, and the third was given as much of the screen as the first.
 *
 * Under the editor rather than beside it, because every part of this refers to
 * the code directly above: the claim is about a line, the evidence trail is a
 * list of lines, and the fix is a change to one of them.
 */
export default function FindingDetail() {
  const [runId] = useRunId();
  const [findingId] = useSelectedFinding();
  const [, setPath] = useOpenFile();
  const [, setLine] = useRevealLine();
  const { phase } = useRunStream();

  const findings = useFindings(runId);
  const knowledge = useKnowledge(runId);
  const apply = useApplyFix(runId);
  const propose = useProposeFix(runId);

  const finding = useMemo(
    () => (findingId ? fromAgent(findings.data?.findings).find((each) => each.id === findingId) : undefined),
    [findings.data, findingId],
  );

  const running = phase === "running" || phase === "starting";
  const go = (file: string, line: number) => {
    void setPath(file);
    void setLine(line > 0 ? line : null);
  };

  if (!finding) {
    return (
      <PanelShell title="문제">
        <EmptyState icon={MousePointerClick} title="왼쪽에서 문제를 고르세요">
          고른 문제의 근거와 고치는 방법이 여기 나옵니다.
        </EmptyState>
      </PanelShell>
    );
  }

  const standing = standingOf(finding);
  const related = knowledge.data && finding.chunkId ? neighbours(knowledge.data, finding.chunkId, 1) : [];

  return (
    <PanelShell
      title={finding.title}
      note={`${finding.cwe ? `${finding.cwe} · ` : ""}${finding.primary.file}:${finding.primary.startLine}`}
      actions={standing && <Verdict standing={standing} confidence={finding.confidence ?? undefined} />}
    >
      <div className="space-y-4 px-3 py-3">
        <section className="space-y-1.5">
          <h3 className="text-2xs text-ink-muted">왜</h3>
          <p className="max-w-prose text-xs leading-relaxed whitespace-pre-wrap text-ink">
            {finding.explanation}
          </p>
        </section>

        {finding.evidence.length > 0 && (
          <section className="space-y-1.5">
            <h3 className="text-2xs text-ink-muted">근거</h3>
            <ol className="space-y-1">
              {finding.evidence.map((step, index) => (
                <li key={index}>
                  <button
                    type="button"
                    onClick={() => go(step.span.file, step.span.startLine)}
                    className={`w-full border-l-2 py-1 pl-2 text-left transition-colors hover:bg-surface-2 ${
                      ROLE_TONE[step.role] ?? "border-l-line-2"
                    }`}
                  >
                    <span className="flex items-center gap-1.5 text-2xs text-ink-faint">
                      <span className="text-ink-muted">{ROLE_LABEL[step.role]}</span>
                      {step.span.startLine > 0 && (
                        <span className="font-mono">
                          {step.span.file}:{step.span.startLine}
                        </span>
                      )}
                    </span>
                    <span className="mt-0.5 block text-xs leading-snug text-ink">{step.note}</span>
                  </button>
                </li>
              ))}
            </ol>
          </section>
        )}

        <section className="space-y-2">
          <h3 className="text-2xs text-ink-muted">고치기</h3>
          {finding.remediation && (
            <p className="max-w-prose text-xs leading-relaxed whitespace-pre-wrap text-ink-muted">
              {finding.remediation}
            </p>
          )}
          {finding.diff ? (
            <div className="space-y-2">
              {/* The patch before the button, always. This writes to the reader's
                  source, and offering to do that without showing what would
                  change asks for a decision nobody can make. */}
              <Patch diff={finding.diff} className="max-h-56" />
              <Button
                size="xs"
                variant="outline"
                disabled={apply.isPending || running}
                onClick={() => apply.mutate(wireId(finding.id))}
              >
                <Wrench />
                {apply.isPending ? "적용하는 중…" : "이대로 고치기"}
              </Button>
            </div>
          ) : (
            <Button
              size="xs"
              variant="outline"
              disabled={propose.isPending || running}
              onClick={() => propose.mutate(wireId(finding.id))}
            >
              <Wrench />
              {propose.isPending ? "만드는 중…" : "고칠 코드 만들기"}
            </Button>
          )}
        </section>

        <Trail finding={finding} />

        {related.length > 0 && (
          <section className="space-y-1.5">
            <h3 className="text-2xs text-ink-muted">관련 코드</h3>
            <ul className="flex flex-wrap gap-1">
              {related.slice(0, 12).map((node) => (
                <li key={node.id}>
                  <button
                    type="button"
                    onClick={() => go(node.file, node.attrs?.start_line ?? 0)}
                    className="rounded-sm border border-line px-1.5 py-0.5 font-mono text-2xs text-ink-muted transition-colors hover:border-line-3 hover:text-ink"
                  >
                    {node.label}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </PanelShell>
  );
}

/**
 * How the checker arrived at this, in one line.
 *
 * The whole record used to sit in a pane of its own, the same size as the answer,
 * open whether or not anybody doubted anything. Most of the time the useful
 * version of it is this: which steps ran, in order. The rest is one link away, in
 * the workspace that is about the checker rather than about your code.
 */
function Trail({ finding }: { finding: UiFinding }) {
  const [runId] = useRunId();
  const threads = useThreads(runId);
  const shape = useGraphShape();

  const chain = useMemo(() => {
    if (!finding.chunkId) return [];
    const units = unitsOf(threads.data?.threads ?? [], shape.data?.steps ?? []);
    const unit = units.find((each) => each.id === finding.chunkId);
    if (!unit) return [];
    return trailOf(unit, claimOf(finding))
      .exchanges.map(labelOf)
      .filter((label, at, all) => all.indexOf(label) === at);
  }, [threads.data, shape.data, finding]);

  if (chain.length === 0) return null;

  return (
    <Disclosure label="어떻게 알았나" tone="aside">
      <div className="mt-1 space-y-1.5 pl-4">
        <p className="text-2xs leading-relaxed text-accent-ink">{chain.join(" → ")}</p>
        <Link
          href={`/agent/machine?run=${runId ?? ""}&finding=${encodeURIComponent(finding.id)}`}
          className="inline-block font-mono text-2xs text-ink-faint underline decoration-dotted hover:text-ink-muted"
        >
          주고받은 내용 전부 보기
        </Link>
      </div>
    </Disclosure>
  );
}
