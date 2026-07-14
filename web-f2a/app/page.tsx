"use client";

import { useMemo, useState } from "react";
import dynamic from "next/dynamic";
import SourcePanel from "@/components/SourcePanel";
import DecisionView from "@/components/DecisionView";
import F2AReport from "@/components/F2AReport";
import { analyze } from "@/lib/api";
import { parseCpg } from "@/lib/cpg";
import { SAMPLES } from "@/lib/samples";
import type { AnalyzeResponse, ViewKey } from "@/lib/types";

// React Flow touches the DOM — load the graph explorer client-only.
const GraphExplorer = dynamic(() => import("@/components/GraphExplorer"), { ssr: false });

type Tab = "decision" | ViewKey | "report";

const GRAPH_TABS: { key: ViewKey; label: string }[] = [
  { key: "ast", label: "AST" },
  { key: "cfg", label: "CFG" },
  { key: "dfg", label: "DFG" },
  { key: "cg", label: "CG" },
  { key: "cpg", label: "CPG" },
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

  const parsed = useMemo(() => (response ? parseCpg(response.cpg) : null), [response]);

  const stats = useMemo(() => {
    if (!parsed) return null;
    const methods = [...parsed.nodes.values()].filter((n) => n.label === "METHOD").length;
    return { vertices: parsed.nodes.size, edges: parsed.edges.length, methods };
  }, [parsed]);

  // The function to pre-select in the graph explorer: whatever the user asked to
  // inspect, else the handler where the source is bound.
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
      setAnalyzedSource(source); // snapshot for concrete code evidence
      setTab("decision");
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

  return (
    <div className="app">
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

      <div className="main">
        <div className="tabs">
          <button className={`tab ${tab === "decision" ? "active" : ""}`} onClick={() => setTab("decision")}>
            판단
            {response && <span className="count">{response.f2a.evidence_packages.length}</span>}
          </button>
          {GRAPH_TABS.map((t) => (
            <button
              key={t.key}
              className={`tab ${tab === t.key ? "active" : ""}`}
              onClick={() => setTab(t.key)}
              disabled={!parsed}
            >
              {t.label}
            </button>
          ))}
          <button
            className={`tab ${tab === "report" ? "active" : ""}`}
            onClick={() => setTab("report")}
            disabled={!response}
          >
            리포트
          </button>
        </div>

        <div className="stage">
          {!response && (
            <div className="empty">
              예제를 불러오거나 소스를 붙여넣은 뒤 <b>분석</b>을 누르세요.
              <br />
              먼저 이해하기 쉬운 <b>판단 결과</b>가 나오고, 각 단계를 누르면 코드 근거를 볼 수 있습니다.
            </div>
          )}

          {response && tab === "decision" && (
            <DecisionView result={response.f2a} source={analyzedSource} onInspect={onInspect} />
          )}
          {response && tab === "report" && <F2AReport result={response.f2a} />}
          {parsed && tab !== "decision" && tab !== "report" && (
            <GraphExplorer cpg={parsed} tab={tab} defaultMethodId={defaultMethodId} />
          )}
        </div>
      </div>
    </div>
  );
}
