"use client";

import Editor, { type OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { annotate, type LineMarker } from "@/lib/annotate";
import type { EvidencePackage, PipelineFunction } from "@/lib/types";

/**
 * Def-use edges drawn on the source -- the old app's /code-viewer.
 *
 * A lens rather than the default view, because its line numbers are inferred:
 * the pipeline DFG carries only each node's code text, so an edge is placed by
 * finding that text in the source and dropped when it appears more than once.
 * F2-A markers on the code canvas come from real CPG lines and are exact.
 */

const TONE_CLASS: Record<LineMarker["tone"], string> = {
  source: "ann-source",
  sink: "ann-sink",
  "check-ok": "ann-check-ok",
  "check-weak": "ann-check-weak",
  flow: "ann-flow",
};

const TONE_LABEL: Record<LineMarker["tone"], string> = {
  source: "유입",
  sink: "위험 지점",
  "check-ok": "검증(충분)",
  "check-weak": "검증(약함)",
  flow: "전파",
};

export default function DataFlowView({
  source,
  language,
  evidence,
  functions,
}: {
  source: string;
  language: string;
  evidence: EvidencePackage[];
  functions: PipelineFunction[] | null;
}) {
  const [fnName, setFnName] = useState<string>("");
  const [showFlow, setShowFlow] = useState(true);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const decorations = useRef<editor.IEditorDecorationsCollection | null>(null);

  const selected = useMemo(
    () => functions?.find((f) => f.function_name === fnName) ?? null,
    [functions, fnName],
  );

  const { markers, links, unplaced } = useMemo(
    () => annotate(evidence, showFlow ? selected : null, source),
    [evidence, selected, source, showFlow],
  );

  const apply = useCallback(() => {
    const instance = editorRef.current;
    if (!instance) return;
    const model = instance.getModel();
    if (!model) return;

    const byLine = new Map<number, LineMarker[]>();
    for (const marker of markers) {
      byLine.set(marker.line, [...(byLine.get(marker.line) ?? []), marker]);
    }
    for (const link of links) {
      const label = link.label ? `데이터 흐름 → ${link.toLine}행 (${link.label})` : `데이터 흐름 → ${link.toLine}행`;
      byLine.set(link.fromLine, [
        ...(byLine.get(link.fromLine) ?? []),
        { line: link.fromLine, tone: "flow", label },
      ]);
    }

    decorations.current?.clear();
    decorations.current = instance.createDecorationsCollection(
      [...byLine.entries()].map(([line, items]) => ({
        range: { startLineNumber: line, startColumn: 1, endLineNumber: line, endColumn: 1 },
        options: {
          isWholeLine: true,
          className: TONE_CLASS[items[0].tone],
          glyphMarginClassName: `ann-glyph ${TONE_CLASS[items[0].tone]}`,
          hoverMessage: items.map((i) => ({ value: `**${TONE_LABEL[i.tone]}** — ${i.label}` })),
        },
      })),
    );
  }, [markers, links]);

  const handleMount: OnMount = (instance) => {
    editorRef.current = instance;
    apply();
  };

  useEffect(apply, [apply]);

  const jump = (line: number) => {
    editorRef.current?.revealLineInCenter(line);
    editorRef.current?.setPosition({ lineNumber: line, column: 1 });
  };

  if (!source.trim()) {
    return (
      <div className="empty" style={{ padding: 24 }}>
        분석한 소스가 없습니다. CPG JSON만 불러온 경우 원본 소스가 없어 표시할 수 없습니다.
      </div>
    );
  }

  return (
    <div className="codeview">
      <div className="codeview-bar">
        <div className="tbfield">
          <span>함수</span>
          <select value={fnName} onChange={(e) => setFnName(e.target.value)}>
            <option value="">— 데이터 흐름 없음 —</option>
            {(functions ?? []).map((f) => (
              <option key={f.function_name} value={f.function_name}>
                {f.function_name}
              </option>
            ))}
          </select>
        </div>
        <label className="tbcheck">
          <input type="checkbox" checked={showFlow} onChange={(e) => setShowFlow(e.target.checked)} />
          데이터 흐름 표시
        </label>
        <span className="tbcount">
          근거 {markers.length}건 · 흐름 {links.length}건
          {unplaced > 0 && ` · 위치 불명 ${unplaced}건`}
        </span>
      </div>

      <div className="codeview-body">
        <div className="codeview-editor">
          <Editor
            height="100%"
            theme="vs-dark"
            language={language === "java" ? "java" : language === "cpp" ? "cpp" : "c"}
            value={source}
            onMount={handleMount}
            options={{
              readOnly: true,
              domReadOnly: true,
              glyphMargin: true,
              minimap: { enabled: false },
              fontSize: 13,
              scrollBeyondLastLine: false,
              automaticLayout: true,
            }}
          />
        </div>

        <aside className="codeview-list">
          {markers.length === 0 && <p className="empty">표시할 근거가 없습니다.</p>}
          {markers.map((m, i) => (
            <button key={`${m.line}-${i}`} className={`ann-row ${TONE_CLASS[m.tone]}`} onClick={() => jump(m.line)}>
              <span className="ann-line">{m.line}</span>
              <span className="ann-tone">{TONE_LABEL[m.tone]}</span>
              <span className="ann-label">{m.label}</span>
            </button>
          ))}
          {unplaced > 0 && (
            <p className="muted small" style={{ padding: "8px 10px" }}>
              데이터 흐름 {unplaced}건은 소스에서 한 줄로 특정할 수 없어 생략했습니다. 파이프라인 DFG는 줄 번호를
              내보내지 않으므로 코드 문자열로 위치를 찾습니다.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
