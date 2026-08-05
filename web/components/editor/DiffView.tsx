"use client";

import { DiffEditor } from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
import type * as Monaco from "monaco-editor";

import { setupMonaco } from "./monaco-setup";
import { followTheme } from "./theme";

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
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!ready || !monacoRef.current) return;
    return followTheme(monacoRef.current, (name) => monacoRef.current?.editor.setTheme(name));
  }, [ready]);

  return (
    <DiffEditor
      original={original}
      modified={modified}
      language={language}
      beforeMount={setupMonaco}
      onMount={(_editor, monaco) => {
        monacoRef.current = monaco;
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
  );
}
