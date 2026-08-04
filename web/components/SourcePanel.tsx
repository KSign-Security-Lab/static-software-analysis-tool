"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiBase } from "@/lib/api";
import { SAMPLES } from "@/lib/samples";
import { looksLikeCpg, unwrapCpgDocument } from "@/lib/cpg";

/** Source extension -> the language value the API expects. */
const EXT_LANG: Record<string, string> = {
  c: "c",
  h: "c",
  cpp: "cpp",
  cc: "cpp",
  cxx: "cpp",
  hpp: "cpp",
  hxx: "cpp",
  java: "java",
};

export default function SourcePanel({
  source,
  setSource,
  language,
  setLanguage,
  loading,
  error,
  onAnalyze,
  onLoadSample,
  onLoadCpg,
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
  onLoadCpg: (cpg: unknown, filename: string) => void;
  stats: { vertices: number; edges: number; methods: number } | null;
}) {
  // Resolve on the client (depends on window.location).
  const [backend, setBackend] = useState("");
  useEffect(() => setBackend(apiBase()), []);

  // Two kinds of drop, which is what the old web/ app did before the merge:
  // a source file fills the editor, and a .json CPG is opened directly. The
  // second matters because `ssat cpg` writes JSON, and without it that output
  // could only be viewed by recompiling the source it came from.
  const fileInput = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);

  const loadFile = useCallback(
    (file: File) => {
      setFileError(null);
      const ext = file.name.split(".").pop()?.toLowerCase() ?? "";

      if (ext === "json") {
        file
          .text()
          .then((text) => {
            const raw: unknown = JSON.parse(text);
            if (!looksLikeCpg(raw)) {
              setFileError("CPG JSON이 아닙니다 (vertices/edges를 찾을 수 없습니다)");
              return;
            }
            onLoadCpg(unwrapCpgDocument(raw), file.name);
          })
          .catch((e: unknown) => setFileError(e instanceof Error ? e.message : String(e)));
        return;
      }

      const detected = EXT_LANG[ext];
      if (!detected) {
        setFileError(`지원하지 않는 확장자입니다: .${ext} (c/cpp/java/json)`);
        return;
      }
      file
        .text()
        .then((text) => {
          setSource(text);
          setLanguage(detected);
        })
        .catch((e: unknown) => setFileError(e instanceof Error ? e.message : String(e)));
    },
    [setSource, setLanguage, onLoadCpg],
  );
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

      <div className="field">
        <label>파일</label>
        <div
          className={`dropzone ${dragging ? "dragging" : ""}`}
          onClick={() => fileInput.current?.click()}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) loadFile(file);
          }}
        >
          소스 또는 CPG JSON을 끌어다 놓거나 클릭해 선택하세요
          <span className="muted small">.c .h .cpp .cc .cxx .hpp .hxx .java · .json (CPG)</span>
        </div>
        <input
          ref={fileInput}
          type="file"
          accept=".c,.h,.cpp,.cc,.cxx,.hpp,.hxx,.java,.json"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) loadFile(file);
            e.target.value = "";
          }}
        />
        {fileError && <div className="error small">{fileError}</div>}
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
