"use client";

import { DiffEditor } from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
import type * as Monaco from "monaco-editor";

import "./monaco-setup";
import { followTheme } from "./theme";
import { useDeferredLayout } from "./use-deferred-layout";

export default function DiffView({
  original,
  modified,
  language = "json",
}: {
  original: string;
  modified: string;
  language?: string;
}) {
  const monacoRef = useRef<typeof Monaco | null>(null);
  const editorRef = useRef<Monaco.editor.IStandaloneDiffEditor | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ready || !monacoRef.current) return;
    return followTheme(monacoRef.current, (name) => monacoRef.current?.editor.setTheme(name));
  }, [ready]);

  const { observe, relayout } = useDeferredLayout(() => editorRef.current?.layout());

  return (
    <div ref={observe} className="h-full min-h-0 w-full">
    <DiffEditor
      original={original}
      modified={modified}
      language={language}
      onMount={(editor, monaco) => {
        editorRef.current = editor;
        monacoRef.current = monaco;
        relayout();
        setReady(true);
      }}
      loading={<p className="p-3 text-2xs text-ink-faint">비교하는 중…</p>}
      options={{
        readOnly: true,
        renderSideBySide: true,
        fontSize: 11,
        fontFamily: "var(--font-mono)",
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
        automaticLayout: true,
        renderOverviewRuler: false,
      }}
    />
    </div>
  );
}
