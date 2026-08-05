"use client";

import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { useCallback, useEffect, useRef, useState } from "react";

import { applyMarkers, evidenceDecorations } from "./markers";
import { setupMonaco } from "./monaco-setup";
import { followTheme } from "./theme";
import type { UiFinding } from "@/lib/model/finding";

/**
 * The editor.
 *
 * The only file in the app that imports `@monaco-editor/react`, so the
 * loader configuration, the theme and the marker plumbing exist once. There
 * used to be two, with divergent option objects and both hardcoded to a dark
 * theme.
 */

export interface CodeEditorProps {
  path: string | null;
  value: string;
  language?: string;
  readOnly?: boolean;
  findings?: UiFinding[];
  selected?: UiFinding | null;
  onChange?: (value: string) => void;
  /** ⌘S from inside the editor, which a window listener may never see. */
  onSave?: () => void;
  onRevealFinding?: (finding: UiFinding) => void;
}

export default function CodeEditor({
  path,
  value,
  language,
  readOnly = false,
  findings = [],
  selected = null,
  onChange,
  onSave,
  onRevealFinding,
}: CodeEditorProps) {
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);
  const decorations = useRef<Monaco.editor.IEditorDecorationsCollection | null>(null);
  const [ready, setReady] = useState(false);

  // Held in refs so the mount callback can stay stable -- Monaco tears the
  // editor down and rebuilds it if `onMount` changes identity. Updated in an
  // effect rather than during render, which is the rule the React Compiler
  // enforces and the reason the old CodeCanvas is on the exemption list.
  const save = useRef(onSave);
  const reveal = useRef(onRevealFinding);
  useEffect(() => {
    save.current = onSave;
    reveal.current = onRevealFinding;
  }, [onSave, onRevealFinding]);

  const onMount = useCallback<OnMount>((editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    decorations.current = editor.createDecorationsCollection([]);

    // Also bound inside the editor: the window listener sees the key during
    // bubble, but Monaco may have handled and stopped it first.
    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => save.current?.());

    setReady(true);
  }, []);

  // Theme, and re-theme whenever the attribute flips.
  useEffect(() => {
    if (!ready || !monacoRef.current) return;
    return followTheme(monacoRef.current, (name) => monacoRef.current?.editor.setTheme(name));
  }, [ready]);

  // Markers follow the findings for this file.
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    const model = editor?.getModel();
    if (!ready || !monaco || !model) return;
    applyMarkers(
      monaco,
      model,
      findings.filter((finding) => finding.primary.file === path),
    );
  }, [ready, findings, path]);

  // The evidence trail lights up only for the selected finding.
  useEffect(() => {
    if (!ready) return;
    decorations.current?.set(evidenceDecorations(selected, path));
    if (selected && selected.primary.file === path && selected.primary.startLine > 0) {
      editorRef.current?.revealLineInCenterIfOutsideViewport(selected.primary.startLine);
      editorRef.current?.setPosition({ lineNumber: selected.primary.startLine, column: 1 });
    }
  }, [ready, selected, path]);

  // Clicking a squiggled line selects that finding, so the editor drives the
  // inspector rather than only being driven by it.
  useEffect(() => {
    const editor = editorRef.current;
    if (!ready || !editor) return;
    const listener = editor.onMouseDown((event) => {
      const line = event.target.position?.lineNumber;
      if (!line) return;
      const hit = findings.find(
        (finding) =>
          finding.primary.file === path &&
          line >= finding.primary.startLine &&
          line <= (finding.primary.endLine || finding.primary.startLine),
      );
      if (hit) reveal.current?.(hit);
    });
    return () => listener.dispose();
  }, [ready, findings, path]);

  return (
    <Editor
      path={path ?? undefined}
      value={value}
      language={language}
      onChange={(next) => onChange?.(next ?? "")}
      onMount={onMount}
      beforeMount={setupMonaco}
      loading={<p className="p-4 text-sm text-ink-faint">편집기를 불러오는 중…</p>}
      options={{
        readOnly,
        fontSize: 13,
        lineHeight: 20,
        fontFamily: "var(--font-mono)",
        fontLigatures: true,
        minimap: { enabled: false },
        // The workbench already has a scrollbar per panel; a second one inside
        // the editor makes the pane look like it is nested twice.
        scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10, useShadows: false },
        scrollBeyondLastLine: false,
        renderLineHighlight: "all",
        smoothScrolling: true,
        automaticLayout: true,
        padding: { top: 10, bottom: 10 },
        overviewRulerBorder: false,
        tabSize: 4,
      }}
    />
  );
}
