"use client";

import { useState } from "react";

import SectionHeader from "@/components/shell/SectionHeader";
import { apiBase } from "@/lib/http";
import { SAMPLES } from "@/lib/samples";

/**
 * Run one pipeline stage and see its raw output -- the old app's /generate
 * page, which the frontend merge dropped.
 *
 * The analyse page runs the whole chain and renders the result. This is the
 * other thing you want when a stage is misbehaving: call it alone and read the
 * JSON it actually returned.
 */

interface Stage {
  key: string;
  path: string;
  label: string;
  note: string;
  /** Whether the endpoint accepts a prebuilt CPG instead of source. */
  acceptsCpg: boolean;
}

const STAGES: Stage[] = [
  { key: "cpg-jpype", path: "/cpg-jpype", label: "CPG (jpype)", note: "소스 → GraphSON, 인프로세스 Joern", acceptsCpg: false },
  { key: "cpg-docker", path: "/cpg-docker", label: "CPG (docker)", note: "소스 → GraphSON, Joern 컨테이너", acceptsCpg: false },
  { key: "template", path: "/template", label: "Template", note: "CPG → 템플릿 노드", acceptsCpg: true },
  { key: "ast", path: "/ast", label: "AST", note: "CPG → 함수별 AST", acceptsCpg: true },
  { key: "dfg", path: "/dfg", label: "DFG", note: "CPG → 함수별 def-use DFG", acceptsCpg: true },
  { key: "analyze-functions", path: "/analyze-functions", label: "AST + DFG", note: "GNN 학습 스키마", acceptsCpg: true },
  { key: "f2a", path: "/f2a", label: "F2-A", note: "CPG → 근거 패키지", acceptsCpg: true },
];

export default function StagesPage() {
  const [stageKey, setStageKey] = useState(STAGES[0].key);
  const [language, setLanguage] = useState(SAMPLES[0].language);
  const [source, setSource] = useState(SAMPLES[0].source);
  const [cpgText, setCpgText] = useState("");
  const [useCpg, setUseCpg] = useState(false);
  const [output, setOutput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [elapsed, setElapsed] = useState<number | null>(null);

  const stage = STAGES.find((s) => s.key === stageKey) ?? STAGES[0];
  const cpgMode = useCpg && stage.acceptsCpg;

  const run = async () => {
    setLoading(true);
    setError(null);
    setOutput("");
    const started = performance.now();
    try {
      let body: unknown;
      if (stage.key === "f2a") {
        body = { cpg: JSON.parse(cpgText) };
      } else if (cpgMode) {
        body = { cpg: JSON.parse(cpgText) };
      } else {
        body = { source, language, filename: `main.${language === "java" ? "java" : language}` };
      }

      const res = await fetch(`${apiBase()}${stage.path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const text = await res.text();
      if (!res.ok) {
        let detail = text;
        try {
          detail = (JSON.parse(text) as { detail?: string }).detail ?? text;
        } catch {
          /* non-JSON error body */
        }
        throw new Error(detail);
      }
      // Pretty-print, but a CPG can be tens of megabytes -- do not try to
      // reformat something that large, just show the head of it.
      setOutput(text.length > 2_000_000 ? text.slice(0, 2_000_000) + "\n… (잘림)" : JSON.stringify(JSON.parse(text), null, 2));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setElapsed(Math.round(performance.now() - started));
      setLoading(false);
    }
  };

  return (
    <>
      <SectionHeader
        title="추출"
        note="CPG · AST · CFG · DFG · 파이프라인"
        views={[
          { href: "/extract", label: "그래프" },
          { href: "/extract/stages", label: "스테이지" },
        ]}
      />
    <main className="stages">
      <div className="stages-input">
        <h2>스테이지 실행</h2>
        <p className="subtitle">파이프라인 단계를 하나씩 호출하고 원본 JSON을 확인합니다.</p>

        <div className="field">
          <label>단계</label>
          <select value={stageKey} onChange={(e) => setStageKey(e.target.value)}>
            {STAGES.map((s) => (
              <option key={s.key} value={s.key}>
                {s.label}
              </option>
            ))}
          </select>
          <span className="muted small">{stage.note}</span>
        </div>

        {stage.acceptsCpg && stage.key !== "f2a" && (
          <label className="tbcheck">
            <input type="checkbox" checked={useCpg} onChange={(e) => setUseCpg(e.target.checked)} />
            소스 대신 CPG JSON 입력
          </label>
        )}

        {stage.key === "f2a" || cpgMode ? (
          <div className="editor">
            <label>CPG JSON</label>
            <textarea
              className="editor-area"
              value={cpgText}
              onChange={(e) => setCpgText(e.target.value)}
              placeholder='{"@type": "tinker:graph", "@value": { "vertices": [...], "edges": [...] }}'
              spellCheck={false}
            />
          </div>
        ) : (
          <>
            <div className="field">
              <label>언어</label>
              <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                <option value="c">C</option>
                <option value="cpp">C++</option>
                <option value="java">Java</option>
              </select>
            </div>
            <div className="field">
              <label>예제</label>
              <select
                defaultValue=""
                onChange={(e) => {
                  const s = SAMPLES.find((x) => x.id === e.target.value);
                  if (s) {
                    setSource(s.source);
                    setLanguage(s.language);
                  }
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
            <div className="editor">
              <label>소스</label>
              <textarea
                className="editor-area"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                spellCheck={false}
              />
            </div>
          </>
        )}

        <button className="btn btn-primary" onClick={run} disabled={loading}>
          {loading ? "실행 중…" : `${stage.label} 실행`}
        </button>
        {error && <div className="error small">{error}</div>}
      </div>

      <div className="stages-output">
        <div className="codeview-bar">
          <span className="tbcount">
            {elapsed !== null && `${elapsed} ms`}
            {output && ` · ${output.length.toLocaleString()} 자`}
          </span>
        </div>
        {output ? <pre className="stages-json">{output}</pre> : <p className="empty">결과가 여기에 표시됩니다.</p>}
      </div>
    </main>
    </>
  );
}
