"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import SourcePanel from "@/components/SourcePanel";
import DecisionView from "@/components/DecisionView";
import F2AReport from "@/components/F2AReport";
import JsonView from "@/components/JsonView";
import { analyze } from "@/lib/api";
import { parseCpg } from "@/lib/cpg";
import { SAMPLES } from "@/lib/samples";
import type { AnalyzeResponse, ViewKey } from "@/lib/types";

// React Flow touches the DOM — load the graph explorer client-only.
const GraphExplorer = dynamic(() => import("@/components/GraphExplorer"), { ssr: false });

type Tab = "decision" | ViewKey | "report" | "json";

const TABS: { key: Tab; label: string }[] = [
  { key: "decision", label: "판단" },
  { key: "ast", label: "AST" },
  { key: "cfg", label: "CFG" },
  { key: "dfg", label: "DFG" },
  { key: "cg", label: "CG" },
  { key: "cpg", label: "CPG" },
  { key: "report", label: "리포트" },
  { key: "json", label: "JSON" },
];

const GRAPH_KEYS: ViewKey[] = ["ast", "cfg", "dfg", "cg", "cpg"];

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

  const onAnalyze = async () => {
    setLoading(true);
    setError(null);
    setFocusFn(null);
    try {
      const res = await analyze({ source, language, filename });
      setResponse(res);
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

  const onInspect = (fn: string) => {
    setFocusFn(fn);
    setTab("dfg");
  };

  const isGraph = GRAPH_KEYS.includes(tab as ViewKey);

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
            >
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
        {response && tab === "report" && <F2AReport result={response.f2a} />}
        {response && tab === "json" && <JsonView result={response.f2a} />}
        {parsed && isGraph && (
          <GraphExplorer cpg={parsed} tab={tab as ViewKey} defaultMethodId={defaultMethodId} />
        )}
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
          stats={stats}
        />
      </aside>
    </div>
  );
}
