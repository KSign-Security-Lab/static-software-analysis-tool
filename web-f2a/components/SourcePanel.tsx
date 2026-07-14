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
    <div className="drawer-body">
      <p className="subtitle">
        소스에서 코드 프로퍼티 그래프를 추출하고 F2-A 근거 파이프라인을 실행합니다.
        <br />
        ssat.cpg(Joern) + ssat.f2a 기반.
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
        <label>소스</label>
        <div className="editor-shell">
          <div className="editor-bar">
            <span className="dots">
              <i />
              <i />
              <i />
            </span>
            <span className="fname">{`main.${language === "cpp" ? "cpp" : language === "java" ? "java" : "c"}`}</span>
          </div>
          <textarea
            className="code"
            spellCheck={false}
            value={source}
            onChange={(e) => setSource(e.target.value)}
            placeholder="C / C++ / Java 소스를 붙여넣으세요…"
          />
        </div>
      </div>

      <div className="drawer-foot">
        <div className="foot-status">
          {error ? (
            <span className="status err">{error}</span>
          ) : loading ? (
            <span className="status">Joern으로 CPG 생성 중…</span>
          ) : stats ? (
            <span className="status ok">
              노드 {stats.vertices}개 · 엣지 {stats.edges}개 · 함수 {stats.methods}개
            </span>
          ) : (
            <span className="status">백엔드 {backend || "…"}</span>
          )}
        </div>
        <button className="primary block" onClick={onAnalyze} disabled={loading || !source.trim()}>
          {loading && <span className="spinner" />}
          {loading ? "분석 중…" : "분석 실행"}
        </button>
      </div>
    </div>
  );
}
