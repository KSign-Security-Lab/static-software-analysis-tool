"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import TargetBar from "@/components/TargetBar";
import Workspace, { type Lens } from "@/components/workspace/Workspace";
import { analyze, analyzeFunctions, f2aFromCpg } from "@/lib/api/ssat";
import { looksLikeCpg, parseCpg, unwrapCpgDocument } from "@/lib/cpg";
import { fromF2A, type UiFinding } from "@/lib/model/finding";
import { SAMPLES } from "@/lib/samples";
import { CPG_VIEW_KEYS, PIPELINE_VIEW_KEYS, type AnalyzeResponse, type PipelineFunction } from "@/lib/types";

const GraphExplorer = dynamic(() => import("@/components/GraphExplorer"), { ssr: false });
const PipelineExplorer = dynamic(() => import("@/components/PipelineExplorer"), { ssr: false });
const F2AReport = dynamic(() => import("@/components/F2AReport"), { ssr: false });
const JsonView = dynamic(() => import("@/components/JsonView"), { ssr: false });
const DataFlowView = dynamic(() => import("@/components/DataFlowView"), { ssr: false });

/**
 * Structural analysis, code-first.
 *
 * The source is the subject and the graphs are lenses over it. This was a bar
 * of eleven tabs with the code nowhere in sight, which made a finding hard to
 * relate to the thing it was about.
 */
export default function AnalyzePage() {
  const [source, setSource] = useState(SAMPLES[0].source);
  const [language, setLanguage] = useState(SAMPLES[0].language);
  const [filename, setFilename] = useState(SAMPLES[0].filename);
  const [analyzed, setAnalyzed] = useState("");
  const [response, setResponse] = useState<AnalyzeResponse | null>(null);
  const [pipelineFns, setPipelineFns] = useState<PipelineFunction[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const parsed = useMemo(() => (response ? parseCpg(response.cpg) : null), [response]);
  const findings: UiFinding[] = useMemo(
    () => (response ? fromF2A(response.f2a, filename) : []),
    [response, filename],
  );

  // Fetched once, lazily: /analyze already returned the CPG, so this reuses it
  // rather than recompiling the source.
  const fetching = useRef(false);
  useEffect(() => {
    if (!response || pipelineFns || fetching.current) return;
    fetching.current = true;
    analyzeFunctions(response.cpg)
      .then((r) => setPipelineFns(r.functions))
      .catch(() => setPipelineFns([]))
      .finally(() => {
        fetching.current = false;
      });
  }, [response, pipelineFns]);

  const run = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await analyze({ source, language, filename });
      setResponse(res);
      setPipelineFns(null);
      setAnalyzed(source);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }, [source, language, filename]);

  // A CPG JSON skips Joern entirely -- there is no source to compile.
  const openCpg = useCallback(async (raw: unknown, name: string) => {
    setLoading(true);
    setError(null);
    try {
      const cpg = unwrapCpgDocument(raw);
      const f2a = await f2aFromCpg(cpg);
      setResponse({ cpg, method_count: 0, f2a });
      setPipelineFns(null);
      setAnalyzed("");
      setFilename(name);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResponse(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadFile = useCallback(
    async (file: File) => {
      setError(null);
      const text = await file.text();
      if (file.name.toLowerCase().endsWith(".json")) {
        const raw: unknown = JSON.parse(text);
        if (!looksLikeCpg(raw)) {
          setError("CPG JSON이 아닙니다 (vertices/edges를 찾을 수 없습니다).");
          return;
        }
        await openCpg(raw, file.name);
        return;
      }
      setSource(text);
      setFilename(file.name);
    },
    [openCpg],
  );

  const lenses: Lens[] = useMemo(() => {
    const out: Lens[] = [];
    if (parsed) {
      for (const key of CPG_VIEW_KEYS) {
        out.push({
          key,
          label: `${key.toUpperCase()}·CPG`,
          render: () => <GraphExplorer cpg={parsed} tab={key} />,
        });
      }
      for (const key of PIPELINE_VIEW_KEYS) {
        out.push({
          key,
          label: `${key.replace("pipeline-", "").toUpperCase()}·파이프라인`,
          render: () =>
            pipelineFns && pipelineFns.length > 0 ? (
              <PipelineExplorer functions={pipelineFns} tab={key} />
            ) : (
              <div className="ws-empty ws-empty-lg">파이프라인 산출물을 불러오는 중…</div>
            ),
        });
      }
    }
    if (analyzed) {
      out.push({
        key: "dataflow",
        label: "데이터 흐름",
        render: () => (
          <DataFlowView
            source={analyzed}
            language={language}
            evidence={response?.f2a.evidence_packages ?? []}
            functions={pipelineFns}
          />
        ),
      });
    }
    if (response) {
      out.push({ key: "report", label: "리포트", render: () => <F2AReport result={response.f2a} /> });
      out.push({ key: "json", label: "JSON", render: () => <JsonView result={response.f2a} /> });
    }
    return out;
  }, [parsed, pipelineFns, response, analyzed, language]);

  // The source is on screen from the first paint, before any analysis: the
  // canvas doubles as the input. Running the analysis adds markers to the very
  // buffer you were looking at rather than swapping it for something else.
  const showing = analyzed || source;

  return (
    <Workspace
      files={[filename]}
      activeFile={filename}
      fileContent={showing}
      editable={!analyzed}
      onEdit={setSource}
      emptyHint={analyzed ? "이 소스에서 발견된 문제가 없습니다." : "‘분석’을 눌러 이 소스를 검사하세요."}
      findings={findings}
      onOpenFile={() => undefined}
      lenses={lenses}
      toolbar={
        <TargetBar
          language={language}
          setLanguage={setLanguage}
          loading={loading}
          onRun={run}
          onLoadFile={loadFile}
          onLoadSample={(id) => {
            const s = SAMPLES.find((x) => x.id === id);
            if (!s) return;
            setSource(s.source);
            setLanguage(s.language);
            setFilename(s.filename);
          }}
          stats={
            parsed
              ? { vertices: parsed.nodes.size, edges: parsed.edges.length, findings: findings.length }
              : null
          }
        />
      }
      status={error ? <div className="ws-error">{error}</div> : null}
    />
  );
}
