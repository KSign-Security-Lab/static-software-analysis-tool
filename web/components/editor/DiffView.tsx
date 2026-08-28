"use client";

import { DiffEditor } from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
import type * as Monaco from "monaco-editor";

// Imported for its side effect: it configures the loader at module time,
// which is the only point early enough. See monaco-setup.ts.
import "./monaco-setup";
import { followTheme } from "./theme";
import { useDeferredLayout } from "./use-deferred-layout";

/**
 * Two versions of the same text, side by side.
 *
 * `DiffEditor` comes from the Monaco wrapper already installed, so this costs
 * an import rather than a dependency -- which is the whole reason to prefer it
 * over rendering two blocks and asking the reader to spot the difference.
 */
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
        // The observer's one guaranteed notification fired before this existed.
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
        // On, unlike the editor's. This mounts when a tab is switched to, so
        // its first measurement happens while the tab is still being laid out
        // and comes back 5px -- a diff collapsed to one red line, which is what
        // shipped. The wrapper's observer fires once, before Monaco exists, and
        // nothing measures again. Monaco's own observer does.
        //
        // The reason this was off is gone: it was fighting the nested panel
        // groups 검사 used to have, and there is one flat group now.
        automaticLayout: true,
        renderOverviewRuler: false,
      }}
    />
    </div>
  );
}
