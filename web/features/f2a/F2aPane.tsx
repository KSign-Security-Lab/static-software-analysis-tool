"use client";

import { useMemo } from "react";

import CodeEditor from "@/components/editor/CodeEditor.lazy";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PanelShell } from "@/components/workbench/PanelShell";
import { fromF2A } from "@/lib/model/finding";
import { useCpgSource } from "../cpg/provider";
import { useSelectedFinding } from "@/lib/run/selection";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import EvidenceReport from "./EvidenceReport";
import JsonLens from "./JsonLens";

const LENSES = ["code", "report", "json"] as const;

/**
 * F2-A: does an untrusted field reach a dangerous sink, and which handler owns it.
 *
 * The centre is the same editor the agent surface uses, with the same markers
 * -- the two engines answer the same question about the same code, so a result
 * from either is read the same way. The report and the raw JSON are lenses
 * over the same selection rather than separate pages.
 */
export default function F2aPane() {
  const cpg = useCpgSource();
  const [selectedId, setSelectedId] = useSelectedFinding();
  const [lens, setLens] = useQueryState(
    "view",
    parseAsStringLiteral(LENSES).withDefault("code").withOptions({ history: "replace" }),
  );

  const findings = useMemo(
    () => (cpg.response ? fromF2A(cpg.response.f2a, cpg.name) : []),
    [cpg.response, cpg.name],
  );
  const selected = useMemo(() => findings.find((each) => each.id === selectedId) ?? null, [findings, selectedId]);

  // Once analysed, the editor shows what was compiled rather than what has
  // been typed since -- markers that point at line 30 of a different text are
  // worse than no markers.
  const readOnly = cpg.analyzed !== null && cpg.analyzed !== "";
  const value = readOnly ? cpg.analyzed! : cpg.text;

  return (
    <PanelShell
      title={cpg.name}
      note={readOnly ? "분석된 소스" : undefined}
      actions={
        <Tabs value={lens} onValueChange={(next) => void setLens(next as (typeof LENSES)[number])}>
          <TabsList variant="line" className="h-7 gap-0 bg-transparent p-0">
            <TabsTrigger value="code" className="px-2 text-2xs">
              코드
            </TabsTrigger>
            <TabsTrigger value="report" className="px-2 text-2xs" disabled={!cpg.response}>
              리포트
            </TabsTrigger>
            <TabsTrigger value="json" className="px-2 text-2xs" disabled={!cpg.response}>
              원본 JSON
            </TabsTrigger>
          </TabsList>
        </Tabs>
      }
      bodyClassName={lens === "code" ? "overflow-hidden" : undefined}
    >
      {lens === "code" && (
        <CodeEditor
          path={cpg.name}
          value={value}
          language={cpg.language}
          readOnly={readOnly}
          findings={findings}
          selected={selected}
          onChange={cpg.setText}
          onRevealFinding={(finding) => void setSelectedId(finding.id)}
        />
      )}
      {lens === "report" && cpg.response && <EvidenceReport result={cpg.response.f2a} />}
      {lens === "json" && cpg.response && <JsonLens value={cpg.response.f2a} />}
    </PanelShell>
  );
}
