"use client";

import Editor, { type OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { useCallback, useEffect, useRef, useState } from "react";

import { useDeferredLayout } from "./use-deferred-layout";

import { applyMarkers, evidenceDecorations } from "./markers";
// Imported for its side effect: it configures the loader at module time,
// which is the only point early enough. See monaco-setup.ts.
import "./monaco-setup";
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
  /**
   * The line to look at, when something other than the selected finding decided.
   *
   * An evidence step, or a neighbour out of the knowledge graph: both are lines
   * that explain a finding without being the line the finding is filed under.
   */
  line?: number | null;
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
  line = null,
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
  }, [ready, selected, path]);

  /**
   * Where to look.
   *
   * An explicit line wins over the selected finding's own. The trail crosses
   * files -- 유입 in one, 위험 지점 in another -- and following it is the reason
   * it is drawn, so a step has to be able to say where it is. Falling back to
   * the claim's line keeps a plain selection behaving as it did.
   */
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

    // A jump within a file you are already looking at changes nothing else on
    // screen, so it has to say where it went. Cleared on a timer rather than
    // left: a permanent wash would sit on top of the evidence decorations and
    // read as a sixth role.
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

  // Monaco's own `automaticLayout` lays out inside a ResizeObserver callback; see
  // use-deferred-layout.ts for why that cost us the panel group's notifications.
  const observe = useDeferredLayout(() => editorRef.current?.layout());

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
        // Off: laid out from the wrapper's own observer, on the next frame.
        automaticLayout: false,
        padding: { top: 10, bottom: 10 },
        overviewRulerBorder: false,
        tabSize: 4,

        // Nobody writes code here. Code goes in by upload or by paste, and is then
        // read: the finding is on a line and the line is what you came to look at.
        // Everything below is an authoring tool, and each one was something that
        // popped up, moved the text or ate a keystroke while somebody was reading.
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
        lightbulb: { enabled: "off" as never },
        matchBrackets: "never",
        bracketPairColorization: { enabled: false },
        occurrencesHighlight: "off",
        selectionHighlight: false,
        dragAndDrop: false,
        contextmenu: false,
        // The one editing affordance kept: a paste has to be undoable.
        find: { addExtraSpaceOnTop: false, seedSearchStringFromSelection: "never" },
      }}
    />
    </div>
  );
}
