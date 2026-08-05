"use client";

import { useMemo } from "react";

import DockTabs from "@/components/workbench/DockTabs";
import KnowledgePanel from "@/features/knowledge/KnowledgePanel";
import { fromAgent } from "@/lib/model/finding";
import { useFindings } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import ProblemsPanel from "./ProblemsPanel";
import { useOpenFile, useSelectedFinding } from "./state";

/** PROBLEMS, filling in as the run streams. */
export default function ProblemsDock() {
  const [runId] = useRunId();
  const [, setPath] = useOpenFile();
  const [selectedId, setSelectedId] = useSelectedFinding();
  const { phase } = useRunStream();

  const findings = useFindings(runId);
  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);

  const hint = !runId
    ? "코드를 넣고 ‘검사 실행’을 누르세요."
    : phase === "running" || phase === "starting"
      ? "검사 중… 결과는 도착하는 대로 나타납니다."
      : "이 코드에서 발견된 결과가 없습니다.";

  return (
    <DockTabs
      scope="agent"
      tabs={[
        {
          id: "problems",
          label: "문제",
          badge: ui.length || undefined,
          content: (
            <ProblemsPanel
              findings={ui}
              selectedId={selectedId}
              emptyHint={hint}
              onSelect={(finding) => {
                void setSelectedId(finding.id);
                if (finding.primary.file) void setPath(finding.primary.file);
              }}
            />
          ),
        },
        {
          id: "graph",
          label: "구조 지도",
          content: <KnowledgePanel />,
        },
      ]}
    />
  );
}
