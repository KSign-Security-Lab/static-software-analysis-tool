"use client";

import { MousePointerClick } from "lucide-react";
import { useMemo } from "react";

import { EmptyState, PanelShell } from "@/components/workbench/PanelShell";
import { Verdict } from "@/components/panel/verdict";
import { fromAgent, standingOf, wireId } from "@/lib/model/finding";
import { useKnowledge } from "@/lib/run/knowledge-queries";
import { useApplyFix, useFindings, useProposeFix } from "@/lib/run/queries";
import { useOpenFile, useRevealLine, useSelectedFinding } from "@/lib/run/selection";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import { Grounds } from "./FindingList";

/**
 * One problem, in full.
 *
 * The list moved to the rail, so this stopped being a list that opens a row and
 * became the row it opens. That is the whole of the change: a finding's grounds
 * used to push every row under it down the pane, and the pane you were reading
 * in was the same pane you were choosing in.
 *
 * Under the editor rather than beside it, because every part of this refers to
 * the code directly above: the claim is about a line, the evidence trail is a
 * list of lines, and the fix is a change to one of them.
 */
export default function FindingPane() {
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
  // Never while a run is in flight: the inspection is reading these files.
  const running = phase === "running" || phase === "starting";

  return (
    <PanelShell
      title={finding.title}
      note={`${finding.cwe ? `${finding.cwe} · ` : ""}${finding.primary.file}:${finding.primary.startLine}`}
      actions={standing && <Verdict standing={standing} confidence={finding.confidence ?? undefined} />}
    >
      <Grounds
        finding={finding}
        knowledge={knowledge.data}
        onNavigate={(file, line) => {
          void setPath(file);
          void setLine(line > 0 ? line : null);
        }}
        onApply={runId && !running ? (each) => apply.mutate(wireId(each.id)) : undefined}
        applying={apply.isPending}
        onPropose={runId && !running ? (each) => propose.mutate(wireId(each.id)) : undefined}
        proposing={propose.isPending}
      />
    </PanelShell>
  );
}
