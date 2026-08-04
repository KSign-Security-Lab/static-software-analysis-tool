"use client";

import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import SourcePanel from "@/components/SourcePanel";
import DecisionView from "@/components/DecisionView";
import F2AReport from "@/components/F2AReport";
import JsonView from "@/components/JsonView";
import { analyze, analyzeFunctions, f2aFromCpg } from "@/lib/api";
import { parseCpg } from "@/lib/cpg";
import { SAMPLES } from "@/lib/samples";
import {
  CPG_VIEW_KEYS,
  PIPELINE_VIEW_KEYS,
  type AnalyzeResponse,
  type CpgViewKey,
  type PipelineFunction,
  type PipelineViewKey,
  type ViewKey,
} from "@/lib/types";

// React Flow touches the DOM — load the graph explorer client-only.
const GraphExplorer = dynamic(() => import("@/components/GraphExplorer"), { ssr: false });
const PipelineExplorer = dynamic(() => import("@/components/PipelineExplorer"), { ssr: false });
// Monaco touches the DOM too.
const CodeView = dynamic(() => import("@/components/CodeView"), { ssr: false });

type Tab = "decision" | ViewKey | "code" | "report" | "json";

// Two groups of graph tabs, deliberately labelled apart. The CPG group is
// Joern's graph projected by edge label; the pipeline group is the SSAT
// extractor's own statement-level output. Both are called "AST" and "DFG" in
// their own worlds, so the UI never shows those words unqualified.
const TABS: { key: Tab; label: string; group?: string }[] = [
  { key: "decision", label: "판단" },
  { key: "ast", label: "AST", group: "CPG" },
  { key: "cfg", label: "CFG", group: "CPG" },
  { key: "dfg", label: "DFG", group: "CPG" },
  { key: "cg", label: "CG", group: "CPG" },
  { key: "cpg", label: "CPG", group: "CPG" },
  { key: "pipeline-ast", label: "AST", group: "파이프라인" },
  { key: "pipeline-dfg", label: "DFG", group: "파이프라인" },
  { key: "code", label: "코드" },
  { key: "report", label: "리포트" },
  { key: "json", label: "JSON" },
];

export default function Home() {
  const [source, setSource] = useState(SAMPLES[0].source);
  const [language, setLanguage] = useState(SAMPLES[0].language);
  const [filename, setFilename] = useState(SAMPLES[0].filename);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<AnalyzeResponse | null>(null);
  const [analyzedSource, setAnalyzedSource] = useState("");
  const [tab, setTab] = useState<Tab>("decision");
  const [focusFn, setFocusFn] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(true); // open on first load
  // Pipeline artifacts are fetched lazily: /analyze already returned the CPG,
  // so opening a pipeline tab reuses it rather than recompiling the source.
  const [pipelineFns, setPipelineFns] = useState<PipelineFunction[] | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);

  const parsed = useMemo(() => (response ? parseCpg(response.cpg) : null), [response]);

  const stats = useMemo(() => {
    if (!parsed) return null;
    const methods = [...parsed.nodes.values()].filter((n) => n.label === "METHOD").length;
    return { vertices: parsed.nodes.size, edges: parsed.edges.length, methods };
  }, [parsed]);

  const defaultMethodId = useMemo(() => {
    if (!parsed) return undefined;
    const want = focusFn ?? response?.f2a.evidence_packages[0]?.code_evidence.source.function;
    if (!want) return undefined;
    for (const [id, n] of parsed.nodes) if (n.label === "METHOD" && n.name === want) return id;
    return undefined;
  }, [parsed, response, focusFn]);

  const onLoadSample = (id: string) => {
    const s = SAMPLES.find((x) => x.id === id);
    if (!s) return;
    setSource(s.source);
    setLanguage(s.language);
    setFilename(s.filename);
  };

  // Open a CPG JSON directly -- the old web/ app's primary input, which the
  // merge dropped. There is no source to compile, so F2-A runs on the uploaded
  // graph and the source pane shows what came with it, if anything.
  const onLoadCpg = async (cpg: unknown, name: string) => {
    setLoading(true);
    setError(null);
    setFocusFn(null);
    try {
      const f2a = await f2aFromCpg(cpg);
      setResponse({ cpg, method_count: 0, f2a });
      setPipelineFns(null);
      setPipelineError(null);
      setAnalyzedSource("");
      setFilename(name);
      setTab("decision");
      setDrawerOpen(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResponse(null);
    } finally {
      setLoading(false);
    }
  };

  const onAnalyze = async () => {
    setLoading(true);
    setError(null);
    setFocusFn(null);
    try {
      const res = await analyze({ source, language, filename });
      setResponse(res);
      setPipelineFns(null);
      setPipelineError(null);
      setAnalyzedSource(source);
      setTab("decision");
      setDrawerOpen(false); // reveal the result full-width
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResponse(null);
    } finally {
      setLoading(false);
    }
  };

  // Fetch pipeline artifacts the first time a pipeline tab is opened.
  useEffect(() => {
    if (!response) return;
    if (!PIPELINE_VIEW_KEYS.includes(tab as PipelineViewKey) && tab !== "code") return;
    if (pipelineFns || pipelineError) return;

    let cancelled = false;
    analyzeFunctions(response.cpg)
      .then((res) => {
        if (!cancelled) setPipelineFns(res.functions);
      })
      .catch((e: unknown) => {
        if (!cancelled) setPipelineError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [tab, response, pipelineFns, pipelineError]);

  const onInspect = (fn: string) => {
    setFocusFn(fn);
    setTab("dfg");
  };

  const isCpgGraph = CPG_VIEW_KEYS.includes(tab as CpgViewKey);
  const isPipelineGraph = PIPELINE_VIEW_KEYS.includes(tab as PipelineViewKey);

  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">F2</div>
          <div className="brand-name">F2-A</div>
        </div>
        <nav className="topnav">
          {TABS.map((t) => (
            <button
              key={t.key}
              className={`tab ${tab === t.key ? "active" : ""}`}
              onClick={() => setTab(t.key)}
              disabled={!response && t.key !== "decision"}
              title={t.group ? `${t.group} · ${t.label}` : t.label}
            >
              {t.group && <span className="tabgroup">{t.group}</span>}
              {t.label}
              {t.key === "decision" && response && (
                <span className="count">{response.f2a.evidence_packages.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="topbar-actions">
          <button className="srcchip" onClick={() => setDrawerOpen(true)} title="소스 편집">
            <span>{filename}</span>
            <span className="edit">✎</span>
          </button>
        </div>
      </header>

      <div className="content">
        {loading && (
          <div className="loadbar">
            <span />
          </div>
        )}

        {!response && !loading && (
          <div className="empty">
            <div className="empty-mark">🛡️</div>
            소스를 입력하고 <b>분석</b>을 실행하세요.
            <br />
            먼저 이해하기 쉬운 <b>판단 결과</b>가 나오고, 각 단계를 누르면 코드 근거를 볼 수 있습니다.
            <div style={{ marginTop: 18 }}>
              <button className="primary" onClick={() => setDrawerOpen(true)}>
                소스 열기
              </button>
            </div>
          </div>
        )}

        {response && tab === "decision" && (
          <DecisionView result={response.f2a} source={analyzedSource} onInspect={onInspect} />
        )}
        {response && tab === "code" && (
          <CodeView
            source={analyzedSource}
            language={language}
            evidence={response.f2a.evidence_packages ?? []}
            functions={pipelineFns}
          />
        )}
        {response && tab === "report" && <F2AReport result={response.f2a} />}
        {response && tab === "json" && <JsonView result={response.f2a} />}
        {parsed && isCpgGraph && (
          <GraphExplorer cpg={parsed} tab={tab as CpgViewKey} defaultMethodId={defaultMethodId} />
        )}
        {isPipelineGraph &&
          (pipelineError ? (
            <div className="empty">
              <p>파이프라인 아티팩트를 가져오지 못했습니다.</p>
              <p className="muted">{pipelineError}</p>
            </div>
          ) : pipelineFns ? (
            <PipelineExplorer
              functions={pipelineFns}
              tab={tab as PipelineViewKey}
              focusFunction={focusFn}
            />
          ) : (
            <div className="empty">불러오는 중…</div>
          ))}
      </div>

      {/* source drawer */}
      <div className={`scrim ${drawerOpen ? "open" : ""}`} onClick={() => setDrawerOpen(false)} />
      <aside className={`drawer ${drawerOpen ? "open" : ""}`} aria-hidden={!drawerOpen}>
        <div className="drawer-head">
          <h2>소스 분석</h2>
          <button className="drawer-close" onClick={() => setDrawerOpen(false)} aria-label="닫기">
            ✕
          </button>
        </div>
        <SourcePanel
          source={source}
          setSource={setSource}
          language={language}
          setLanguage={setLanguage}
          loading={loading}
          error={error}
          onAnalyze={onAnalyze}
          onLoadSample={onLoadSample}
          onLoadCpg={onLoadCpg}
          stats={stats}
        />
      </aside>
    </div>
  );
}
