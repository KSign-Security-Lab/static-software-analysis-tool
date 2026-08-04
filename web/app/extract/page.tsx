"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useRef, useState } from "react";

import { CpgSourceBar, useCpgSource } from "@/components/CpgSource";
import SectionHeader from "@/components/shell/SectionHeader";
import Workspace, { type Lens } from "@/components/workspace/Workspace";
import { analyzeFunctions } from "@/lib/api/ssat";
import { parseCpg } from "@/lib/cpg";
import { CPG_VIEW_KEYS, PIPELINE_VIEW_KEYS, type PipelineFunction } from "@/lib/types";

const GraphExplorer = dynamic(() => import("@/components/GraphExplorer"), { ssr: false });
const PipelineExplorer = dynamic(() => import("@/components/PipelineExplorer"), { ssr: false });
const DataFlowView = dynamic(() => import("@/components/DataFlowView"), { ssr: false });

const SECTION_VIEWS = [
  { href: "/extract", label: "그래프" },
  { href: "/extract/stages", label: "스테이지" },
];

/**
 * Extraction: what the front end actually built out of the source.
 *
 * Two vocabularies that both say "AST" and "DFG", so they are labelled apart.
 * CPG views are Joern's graph projected by edge label; pipeline views are the
 * SSAT extractor's own statement-level output.
 */
export default function ExtractPage() {
  const cpg = useCpgSource();
  const [functions, setFunctions] = useState<PipelineFunction[] | null>(null);

  const parsed = useMemo(() => (cpg.response ? parseCpg(cpg.response.cpg) : null), [cpg.response]);

  // Reuses the CPG /analyze already returned rather than recompiling.
  const fetching = useRef(false);
  useEffect(() => {
    if (!cpg.response || functions || fetching.current) return;
    fetching.current = true;
    analyzeFunctions(cpg.response.cpg)
      .then((r) => setFunctions(r.functions))
      .catch(() => setFunctions([]))
      .finally(() => {
        fetching.current = false;
      });
  }, [cpg.response, functions]);

  const lenses: Lens[] = useMemo(() => {
    const out: Lens[] = [];
    if (parsed) {
      for (const key of CPG_VIEW_KEYS) {
        out.push({ key, label: `${key.toUpperCase()}`, render: () => <GraphExplorer cpg={parsed} tab={key} /> });
      }
      for (const key of PIPELINE_VIEW_KEYS) {
        out.push({
          key,
          label: `${key.replace("pipeline-", "").toUpperCase()} (파이프라인)`,
          render: () =>
            functions && functions.length > 0 ? (
              <PipelineExplorer functions={functions} tab={key} />
            ) : (
              <div className="ws-empty ws-empty-lg">파이프라인 산출물을 불러오는 중…</div>
            ),
        });
      }
    }
    if (cpg.analyzed) {
      out.push({
        key: "dataflow",
        label: "데이터 흐름",
        render: () => (
          <DataFlowView
            source={cpg.analyzed}
            language={cpg.language}
            evidence={cpg.response?.f2a.evidence_packages ?? []}
            functions={functions}
          />
        ),
      });
    }
    return out;
  }, [parsed, functions, cpg.analyzed, cpg.language, cpg.response]);

  return (
    <>
      <SectionHeader title="추출" note="CPG · AST · CFG · DFG · 파이프라인" views={SECTION_VIEWS}>
        <CpgSourceBar
          state={cpg}
          meta={
            parsed
              ? `노드 ${parsed.nodes.size.toLocaleString()} · 엣지 ${parsed.edges.length.toLocaleString()}`
              : undefined
          }
        />
      </SectionHeader>

      <Workspace
        files={[cpg.filename]}
        activeFile={cpg.filename}
        fileContent={cpg.analyzed || cpg.source}
        findings={[]}
        onOpenFile={() => undefined}
        lenses={lenses}
        editable={!cpg.analyzed}
        onEdit={cpg.setSource}
        emptyHint="추출은 결과 목록이 아니라 그래프로 봅니다. 위 렌즈를 선택하세요."
        status={cpg.error ? <div className="ws-error">{cpg.error}</div> : null}
      />
    </>
  );
}
