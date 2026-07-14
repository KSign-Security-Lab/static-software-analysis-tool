"use client";

import { useEffect, useState } from "react";
import { apiBase } from "@/lib/api";
import { SAMPLES } from "@/lib/samples";

export default function SourcePanel({
  source,
  setSource,
  language,
  setLanguage,
  loading,
  error,
  onAnalyze,
  onLoadSample,
  stats,
}: {
  source: string;
  setSource: (s: string) => void;
  language: string;
  setLanguage: (s: string) => void;
  loading: boolean;
  error: string | null;
  onAnalyze: () => void;
  onLoadSample: (id: string) => void;
  stats: { vertices: number; edges: number; methods: number } | null;
}) {
  // Resolve on the client (depends on window.location).
  const [backend, setBackend] = useState("");
  useEffect(() => setBackend(apiBase()), []);
  return (
    <div className="sidebar">
      <h1>F2-A 테스트 웹</h1>
      <p className="subtitle">
        소스에서 <b>CPG · AST · CG · DFG · CFG</b> 를 추출하고 F2-A 근거 파이프라인을
        실행합니다. ssat.cpg(Joern) + ssat.f2a 기반.
      </p>

      <div className="field">
        <label>예제</label>
        <select
          defaultValue=""
          onChange={(e) => {
            if (e.target.value) onLoadSample(e.target.value);
          }}
        >
          <option value="">— 예제 불러오기 —</option>
          {SAMPLES.map((s) => (
            <option key={s.id} value={s.id}>
              {s.label}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        <label>언어</label>
        <select value={language} onChange={(e) => setLanguage(e.target.value)}>
          <option value="c">C</option>
          <option value="cpp">C++</option>
          <option value="java">Java</option>
        </select>
      </div>

      <div className="editor">
        <label style={{ fontSize: 12, color: "var(--muted)", marginBottom: 4 }}>소스</label>
        <textarea
          className="code"
          spellCheck={false}
          value={source}
          onChange={(e) => setSource(e.target.value)}
          placeholder="C / C++ / Java 소스를 붙여넣으세요…"
        />
      </div>

      <div className="actions">
        <button className="primary" onClick={onAnalyze} disabled={loading || !source.trim()}>
          {loading ? "분석 중…" : "분석"}
        </button>
        {error ? (
          <span className="status err">{error}</span>
        ) : loading ? (
          <span className="status">Joern으로 CPG 생성 중…</span>
        ) : stats ? (
          <span className="status ok">
            노드 {stats.vertices}개 · 엣지 {stats.edges}개 · 함수 {stats.methods}개
          </span>
        ) : (
          <span className="status">백엔드: {backend || "…"}</span>
        )}
      </div>
    </div>
  );
}
