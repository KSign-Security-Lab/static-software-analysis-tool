"use client";

import { useMemo } from "react";

import DockTabs from "@/components/workbench/DockTabs";
import { fromF2A } from "@/lib/model/finding";
import ProblemsPanel from "@/features/findings/ProblemsPanel";
import { useSelectedFinding } from "@/lib/run/selection";
import { useCpgSource } from "../cpg/provider";

/** The same findings list the agent surface uses; only the engine differs. */
export default function F2aDock() {
  const cpg = useCpgSource();
  const [selectedId, setSelectedId] = useSelectedFinding();

  const findings = useMemo(
    () => (cpg.response ? fromF2A(cpg.response.f2a, cpg.name) : []),
    [cpg.response, cpg.name],
  );

  return (
    <DockTabs
      tabs={[
        {
          id: "problems",
          label: "근거",
          badge: findings.length || undefined,
          content: (
            <ProblemsPanel
              findings={findings}
              selectedId={selectedId}
              emptyHint={cpg.response ? "이 소스에서 발견된 근거가 없습니다." : "‘분석’을 눌러 근거를 추적하세요."}
              onSelect={(finding) => void setSelectedId(finding.id)}
            />
          ),
        },
      ]}
    />
  );
}
