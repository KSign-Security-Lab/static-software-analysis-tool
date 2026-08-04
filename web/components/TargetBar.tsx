"use client";

import { useRef } from "react";

import { SAMPLES } from "@/lib/samples";

/**
 * What is being analysed, and how to change it.
 *
 * A single strip rather than a drawer: the target is one line of information
 * and it should not compete with the code for space.
 */
export default function TargetBar({
  language,
  setLanguage,
  loading,
  onRun,
  onLoadFile,
  onLoadSample,
  stats,
}: {
  language: string;
  setLanguage: (s: string) => void;
  loading: boolean;
  onRun: () => void;
  onLoadFile: (file: File) => void;
  onLoadSample: (id: string) => void;
  stats: { vertices: number; edges: number; findings: number } | null;
}) {
  const fileInput = useRef<HTMLInputElement>(null);

  return (
    <div className="target">
      <select
        className="target-select"
        defaultValue=""
        onChange={(e) => {
          if (e.target.value) onLoadSample(e.target.value);
        }}
      >
        <option value="">예제 선택…</option>
        {SAMPLES.map((s) => (
          <option key={s.id} value={s.id}>
            {s.label}
          </option>
        ))}
      </select>

      <select className="target-select" value={language} onChange={(e) => setLanguage(e.target.value)}>
        <option value="c">C</option>
        <option value="cpp">C++</option>
        <option value="java">Java</option>
      </select>

      <button type="button" className="btn" onClick={() => fileInput.current?.click()}>
        파일 열기
      </button>
      <input
        ref={fileInput}
        type="file"
        hidden
        accept=".c,.h,.cpp,.cc,.cxx,.hpp,.hxx,.java,.json"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onLoadFile(file);
          e.target.value = "";
        }}
      />

      <button type="button" className="btn btn-primary" onClick={onRun} disabled={loading}>
        {loading ? "분석 중…" : "분석"}
      </button>

      {stats && (
        <span className="target-stats">
          노드 {stats.vertices.toLocaleString()} · 엣지 {stats.edges.toLocaleString()} · 결과 {stats.findings}
        </span>
      )}
      <span className="target-hint">소스 파일 또는 CPG JSON · 아래 편집기에서 바로 수정할 수 있습니다</span>
    </div>
  );
}
