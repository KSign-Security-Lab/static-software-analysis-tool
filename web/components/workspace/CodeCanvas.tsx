"use client";

import Editor, { type OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { useCallback, useEffect, useRef } from "react";

import { ROLE_LABEL, markerSeverity, type UiFinding } from "@/lib/model/finding";

/**
 * The source, with everything known about it drawn on top.
 *
 * Findings become Monaco markers -- squiggle, gutter, hover and problems list
 * all come from one array, which is the reason the editor is Monaco. The
 * selected finding's evidence becomes dimmer decorations so the sink reads
 * differently from the trail that leads to it.
 *
 * Editable only before a target exists, when the canvas is also the input.
 * Once something has been analysed it is read-only: nothing here writes to
 * your files.
 */

const OWNER = "ssat";

/** Extension -> Monaco language id. */
const LANGUAGES: Record<string, string> = {
  c: "c",
  h: "c",
  cc: "cpp",
  cpp: "cpp",
  cxx: "cpp",
  hpp: "cpp",
  hh: "cpp",
  java: "java",
  py: "python",
  js: "javascript",
  jsx: "javascript",
  ts: "typescript",
  tsx: "typescript",
  go: "go",
  rs: "rust",
  cs: "csharp",
  json: "json",
};

export function languageOf(path: string): string {
  return LANGUAGES[path.split(".").pop()?.toLowerCase() ?? ""] ?? "plaintext";
}

export default function CodeCanvas({
  path,
  content,
  findings,
  selected,
  onSelect,
  editable = false,
  onChange,
  placeholder,
}: {
  path: string | null;
  content: string;
  findings: UiFinding[];
  selected: UiFinding | null;
  onSelect: (id: string) => void;
  /** Before anything is analysed the canvas *is* the input, so you edit here. */
  editable?: boolean;
  onChange?: (value: string) => void;
  placeholder?: string;
}) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Parameters<OnMount>[1] | null>(null);
  const decorations = useRef<editor.IEditorDecorationsCollection | null>(null);
  const findingsRef = useRef(findings);
  findingsRef.current = findings;

  const paint = useCallback(() => {
    const instance = editorRef.current;
    const monaco = monacoRef.current;
    if (!instance || !monaco || !path) return;
    const model = instance.getModel();
    if (!model) return;

    monaco.editor.setModelMarkers(
      model,
      OWNER,
      findings
        .filter((f) => f.primary.file === path)
        .map((f) => ({
          startLineNumber: f.primary.startLine,
          startColumn: f.primary.startColumn,
          endLineNumber: f.primary.endLine,
          endColumn: Math.max(f.primary.endColumn, f.primary.startColumn + 1),
          message: `${f.title}${f.verified === false ? " (미검증)" : ""}\n\n${f.explanation}`,
          severity: markerSeverity(f.severity),
          source: f.cwe ?? f.engine,
          code: f.id,
        })),
    );

    decorations.current?.clear();
    decorations.current = instance.createDecorationsCollection(
      (selected?.evidence ?? [])
        .filter((e) => e.span.file === path)
        .map((e) => ({
          range: {
            startLineNumber: e.span.startLine,
            startColumn: e.span.startColumn,
            endLineNumber: e.span.endLine,
            endColumn: Math.max(e.span.endColumn, e.span.startColumn + 1),
          },
          options: {
            isWholeLine: e.span.startColumn <= 1,
            className: `ev-${e.role}`,
            hoverMessage: { value: `**${ROLE_LABEL[e.role]}** — ${e.note}` },
          },
        })),
    );
  }, [findings, selected, path]);

  const handleMount: OnMount = (instance, monaco) => {
    editorRef.current = instance;
    monacoRef.current = monaco;
    // Monaco has no "marker clicked" event, so the cursor position is matched
    // against marker ranges instead.
    instance.onMouseDown((event) => {
      const line = event.target.position?.lineNumber;
      if (!line) return;
      const hit = findingsRef.current.find(
        (f) => f.primary.file === path && line >= f.primary.startLine && line <= f.primary.endLine,
      );
      if (hit) onSelect(hit.id);
    });
    paint();
  };

  useEffect(paint, [paint]);

  useEffect(() => {
    const instance = editorRef.current;
    if (!instance || !selected || selected.primary.file !== path) return;
    instance.revealLineInCenter(selected.primary.startLine);
  }, [selected, path]);

  if (!path) {
    return <div className="ws-empty ws-empty-lg">{placeholder ?? "왼쪽에서 파일을 선택하세요."}</div>;
  }

  return (
    <Editor
      height="100%"
      theme="vs-dark"
      path={path}
      language={languageOf(path)}
      value={content}
      onMount={handleMount}
      onChange={(value) => onChange?.(value ?? "")}
      options={{
        readOnly: !editable,
        domReadOnly: !editable,
        minimap: { enabled: true, size: "fill" },
        fontSize: 13,
        lineNumbers: "on",
        glyphMargin: true,
        scrollBeyondLastLine: false,
        smoothScrolling: true,
        automaticLayout: true,
      }}
    />
  );
}
