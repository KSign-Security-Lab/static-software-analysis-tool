"use client";

import Editor, { type Monaco, type OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { useCallback, useEffect, useRef } from "react";

import type { Finding } from "@/lib/agent-schema";
import { evidenceDecorationsFor, markersFor } from "@/lib/markers";

/**
 * Monaco, wired to findings.
 *
 * Findings become markers (squiggle + gutter + hover + problems list) and the
 * selected finding's evidence becomes dimmer inline decorations, so the sink
 * and the trail leading to it read as different things.
 *
 * The editor is read-only: this build shows a proposed fix but never applies
 * one, and an editable buffer would imply otherwise.
 */

export interface CodeEditorProps {
  path: string | null;
  content: string;
  language: string;
  findings: Finding[];
  selected: Finding | null;
  onSelectFinding: (id: string) => void;
}

const MARKER_OWNER = "agent";

export function CodeEditor({
  path,
  content,
  language,
  findings,
  selected,
  onSelectFinding,
}: CodeEditorProps) {
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<Monaco | null>(null);
  const decorationsRef = useRef<editor.IEditorDecorationsCollection | null>(null);

  const applyMarkers = useCallback(() => {
    const monaco = monacoRef.current;
    const instance = editorRef.current;
    if (!monaco || !instance || !path) return;
    const model = instance.getModel();
    if (!model) return;

    monaco.editor.setModelMarkers(model, MARKER_OWNER, markersFor(findings, path));

    decorationsRef.current?.clear();
    decorationsRef.current = instance.createDecorationsCollection(
      evidenceDecorationsFor(selected, path),
    );
  }, [findings, selected, path]);

  const handleMount: OnMount = (instance, monaco) => {
    editorRef.current = instance;
    monacoRef.current = monaco;

    // Clicking a squiggle should open that finding's panel. Monaco has no
    // "marker clicked" event, so the cursor position is matched against marker
    // ranges instead.
    instance.onMouseDown((event) => {
      const position = event.target.position;
      if (!position || !path) return;
      const hit = findings.find((finding) => {
        const span = finding.primary;
        if (span.file !== path) return false;
        return (
          position.lineNumber >= span.start_line && position.lineNumber <= span.end_line
        );
      });
      if (hit) onSelectFinding(hit.id);
    });

    applyMarkers();
  };

  useEffect(applyMarkers, [applyMarkers]);

  // Reveal the selected finding, including when selecting it switched files.
  useEffect(() => {
    const instance = editorRef.current;
    if (!instance || !selected || !path) return;
    if (selected.primary.file !== path) return;
    instance.revealLineInCenter(selected.primary.start_line);
    instance.setPosition({
      lineNumber: selected.primary.start_line,
      column: selected.primary.start_column,
    });
  }, [selected, path]);

  if (!path) {
    return (
      <div className="editor-empty">
        <p>왼쪽에서 파일을 선택하세요.</p>
      </div>
    );
  }

  return (
    <Editor
      height="100%"
      theme="vs-dark"
      path={path}
      language={language}
      value={content}
      onMount={handleMount}
      options={{
        readOnly: true,
        domReadOnly: true,
        minimap: { enabled: true, size: "fill" },
        fontSize: 13,
        fontFamily: 'var(--mono, "JetBrains Mono", monospace)',
        lineNumbers: "on",
        renderLineHighlight: "line",
        scrollBeyondLastLine: false,
        smoothScrolling: true,
        glyphMargin: true,
        automaticLayout: true,
      }}
    />
  );
}
