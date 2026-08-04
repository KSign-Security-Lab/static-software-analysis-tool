"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";

import { CpgSourceBar, useCpgSource } from "@/components/CpgSource";
import SectionHeader from "@/components/shell/SectionHeader";
import Workspace, { type Lens } from "@/components/workspace/Workspace";
import { fromF2A, type UiFinding } from "@/lib/model/finding";

const F2AReport = dynamic(() => import("@/components/F2AReport"), { ssr: false });
const JsonView = dynamic(() => import("@/components/JsonView"), { ssr: false });

/**
 * F2-A: does an untrusted OCPP field reach a dangerous sink, and which handler
 * owns it.
 *
 * Its own section rather than a tab beside the graphs. The graphs are how the
 * CPG is built; this is a verdict with evidence, and the two are read for
 * different reasons.
 */
export default function F2aPage() {
  const cpg = useCpgSource();

  const findings: UiFinding[] = useMemo(
    () => (cpg.response ? fromF2A(cpg.response.f2a, cpg.filename) : []),
    [cpg.response, cpg.filename],
  );

  const lenses: Lens[] = useMemo(() => {
    if (!cpg.response) return [];
    return [
      { key: "report", label: "리포트", render: () => <F2AReport result={cpg.response!.f2a} /> },
      { key: "json", label: "원본 JSON", render: () => <JsonView result={cpg.response!.f2a} /> },
    ];
  }, [cpg.response]);

  const handlers = cpg.response?.f2a.handler_maps?.length ?? 0;

  return (
    <>
      <SectionHeader title="F2-A" note="핸들러 해석과 근거 추적">
        <CpgSourceBar
          state={cpg}
          meta={cpg.response ? `핸들러 ${handlers} · 근거 ${findings.length}` : undefined}
        />
      </SectionHeader>

      <Workspace
        files={[cpg.filename]}
        activeFile={cpg.filename}
        fileContent={cpg.analyzed || cpg.source}
        findings={findings}
        onOpenFile={() => undefined}
        lenses={lenses}
        editable={!cpg.analyzed}
        onEdit={cpg.setSource}
        emptyHint={
          cpg.analyzed ? "이 소스에서 발견된 근거가 없습니다." : "‘분석’을 눌러 근거를 추적하세요."
        }
        status={cpg.error ? <div className="ws-error">{cpg.error}</div> : null}
      />
    </>
  );
}
