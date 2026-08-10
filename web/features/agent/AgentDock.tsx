"use client";

import { useMemo } from "react";

import { PanelShell } from "@/components/workbench/PanelShell";
import { fromAgent } from "@/lib/model/finding";
import { useKnowledge } from "@/lib/run/knowledge-queries";
import { useFindings, useRun } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useOpenFile, useSelectedFinding } from "@/lib/run/selection";
import { useRunId } from "@/lib/run/use-run-id";
import FindingList from "./FindingList";

/**
 * The bottom pane: what the run found. One thing, no tab strip.
 *
 * It had three tabs, and they were not three of a kind: 문제 is the answer, and
 * the other two were a state debugger and a graph canvas. A result list sharing a
 * strip with two developer tools meant the answer was a tab you had to pick. Those
 * two are off the tab strip entirely now -- they open from the command palette,
 * which is where a tool you reach for once a month belongs.
 *
 * A row opens in place to show why: the explanation, the evidence trail, the fix.
 * That used to need a third pane on the far side of the window, which was empty
 * until you had clicked something and replaced whatever you were reading when you
 * did.
 */
export default function AgentDock() {
  const [runId] = useRunId();
  const [, setPath] = useOpenFile();
  const [findingId, setFindingId] = useSelectedFinding();

  const { phase } = useRunStream();
  const findings = useFindings(runId);
  const knowledge = useKnowledge(runId);
  const run = useRun(runId);

  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);
  const running = phase === "running" || phase === "starting";

  return (
    <PanelShell title="문제" note={ui.length > 0 ? `${ui.length}건` : undefined}>
      <FindingList
        findings={ui}
        knowledge={knowledge.data}
        openId={findingId}
        onOpen={(finding) => {
          void setFindingId(finding?.id ?? null);
          // A finding is a claim about a line, so show the line.
          if (finding?.primary.file) void setPath(finding.primary.file);
        }}
        onNavigate={(file) => void setPath(file)}
        emptyHint={
          !runId
            ? "왼쪽 탐색기에 코드를 넣고 ‘검사 실행’을 누르세요."
            : running
              ? "검사 중입니다. 결과는 도착하는 대로 나타납니다."
              : run.data?.started
                ? "이 코드에서는 취약점을 찾지 못했습니다. 오른쪽 대화에서 무엇을 어떻게 살펴봤는지 확인할 수 있습니다."
                : "아직 검사하지 않았습니다. ‘검사 실행’을 누르세요."
        }
      />
    </PanelShell>
  );
}
