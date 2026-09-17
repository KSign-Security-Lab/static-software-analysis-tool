"use client";

import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { useCallback, useEffect, useRef, useState } from "react";

import { useDeferredLayout } from "./use-deferred-layout";

import { applyMarkers, evidenceDecorations, quickFixes } from "./markers";
import "./monaco-setup";
import { followTheme } from "./theme";
import type { UiFinding } from "@/lib/model/finding";

export interface CodeEditorProps {
  path: string | null;
  value: string;
  language?: string;
  readOnly?: boolean;
  density?: "compact" | "comfortable";
  findings?: UiFinding[];
  selected?: UiFinding | null;
  line?: number | null;
  onChange?: (value: string) => void;
  onSave?: () => void;
  onRevealFinding?: (finding: UiFinding) => void;
}

export default function CodeEditor({
  path,
  value,
  language,
  readOnly = false,
  density = "compact",
  findings = [],
  selected = null,
  line = null,
  onChange,
  onSave,
  onRevealFinding,
}: CodeEditorProps) {
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);
  const decorations = useRef<Monaco.editor.IEditorDecorationsCollection | null>(null);
  const [ready, setReady] = useState(false);

  const save = useRef(onSave);
  const reveal = useRef(onRevealFinding);
  useEffect(() => {
    save.current = onSave;
    reveal.current = onRevealFinding;
  }, [onSave, onRevealFinding]);

  const { observe, relayout } = useDeferredLayout(() => editorRef.current?.layout());

  const onMount = useCallback<OnMount>(
    (editor, monaco) => {
      editorRef.current = editor;
      monacoRef.current = monaco;
      decorations.current = editor.createDecorationsCollection([]);

      editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => save.current?.());

      relayout();
      setReady(true);
    },
    [relayout],
  );

  useEffect(() => {
    if (!ready || !monacoRef.current) return;
    return followTheme(monacoRef.current, (name) => monacoRef.current?.editor.setTheme(name));
  }, [ready]);

  useEffect(() => {
    const monaco = monacoRef.current;
    const model = editorRef.current?.getModel();
    if (!ready || !monaco || !model) return;

    const mine = findings.filter((finding) => finding.primary.file === path && finding.replacement);
    if (mine.length === 0) return;

    const provider = monaco.languages.registerCodeActionProvider(model.getLanguageId(), {
      provideCodeActions: (target, range) =>
        target.uri.toString() === model.uri.toString()
          ? quickFixes(monaco, model, mine, range)
          : { actions: [], dispose: () => {} },
    });
    return () => provider.dispose();
  }, [ready, findings, path]);

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

  useEffect(() => {
    if (!ready) return;
    decorations.current?.set(evidenceDecorations(selected, path));
  }, [ready, selected, path]);

  const target =
    line && line > 0
      ? line
      : selected && selected.primary.file === path && selected.primary.startLine > 0
        ? selected.primary.startLine
        : 0;

  useEffect(() => {
    const editor = editorRef.current;
    if (!ready || !editor || target <= 0) return;

    editor.revealLineInCenterIfOutsideViewport(target);
    editor.setPosition({ lineNumber: target, column: 1 });

    const flash = editor.createDecorationsCollection([
      {
        range: { startLineNumber: target, startColumn: 1, endLineNumber: target, endColumn: 1 },
        options: { isWholeLine: true, className: "ssat-jump" },
      },
    ]);
    const timer = window.setTimeout(() => flash.clear(), 1200);
    return () => {
      window.clearTimeout(timer);
      flash.clear();
    };
  }, [ready, target, path]);

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
    <div ref={observe} className="h-full min-h-0 w-full">
    <Editor
      path={path ?? undefined}
      value={value}
      language={language}
      onChange={(next) => onChange?.(next ?? "")}
      onMount={onMount}
      loading={<p className="p-4 text-sm text-ink-faint">편집기를 불러오는 중…</p>}
      options={{
        readOnly,
        fontSize: density === "comfortable" ? 14 : 13,
        lineHeight: density === "comfortable" ? 24 : 20,
        fontFamily: "var(--font-mono)",
        fontLigatures: true,
        minimap: { enabled: false },
        scrollbar: { verticalScrollbarSize: 10, horizontalScrollbarSize: 10, useShadows: false },
        scrollBeyondLastLine: false,
        renderLineHighlight: "all",
        smoothScrolling: true,
        automaticLayout: false,
        padding: { top: 10, bottom: 10 },
        overviewRulerBorder: false,
        tabSize: 4,

        quickSuggestions: false,
        suggestOnTriggerCharacters: false,
        wordBasedSuggestions: "off",
        parameterHints: { enabled: false },
        acceptSuggestionOnEnter: "off",
        tabCompletion: "off",
        snippetSuggestions: "none",
        codeLens: false,
        folding: false,
        links: false,
        lightbulb: { enabled: "onCode" as never },
        matchBrackets: "never",
        bracketPairColorization: { enabled: false },
        occurrencesHighlight: "off",
        selectionHighlight: false,
        dragAndDrop: false,
        contextmenu: false,
        find: { addExtraSpaceOnTop: false, seedSearchStringFromSelection: "never" },
      }}
    />
    </div>
  );
}
