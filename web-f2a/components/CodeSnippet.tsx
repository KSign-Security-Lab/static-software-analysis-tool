"use client";

import { useMemo } from "react";
import { buildGroups, sourceLines, type CodeRef } from "@/lib/code";

/**
 * Concrete code evidence: renders the referenced lines from the analyzed source
 * with line numbers, highlighting + captioning the exact lines a finding rests
 * on. Falls back to the raw code tokens if the source/lines aren't available.
 */
export default function CodeSnippet({ source, refs }: { source: string; refs: CodeRef[] }) {
  const lines = useMemo(() => (source ? sourceLines(source) : []), [source]);
  const groups = useMemo(() => buildGroups(refs, lines.length), [refs, lines.length]);

  // Fallback: no usable source lines → show the raw tokens F2-A matched.
  if (groups.length === 0) {
    const raws = refs.filter((r) => r.raw);
    if (raws.length === 0) return null;
    return (
      <div className="snips">
        {raws.map((r, i) => (
          <div key={i} className="rawline">
            <code className={`tone-${r.tone}`}>{r.raw}</code>
            <span className="cap">{r.caption}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="snips">
      {groups.map((g, gi) => (
        <div className="codeblock" key={gi}>
          <div className="codeblock-bar">
            <span className="dots">
              <i />
              <i />
              <i />
            </span>
            <span className="cb-label">코드 근거 · L{g.start}–{g.end}</span>
          </div>
          <pre className="snip">
            {Array.from({ length: g.end - g.start + 1 }, (_, k) => {
              const n = g.start + k;
              const ref = g.refs.get(n);
              const text = lines[n - 1] ?? "";
              return (
                <div key={n} className={`cline ${ref ? "hl tone-" + ref.tone : ""}`}>
                  <span className="ln">{n}</span>
                  <span className="ct">{text || " "}</span>
                  {ref && <span className="cap">{ref.caption}</span>}
                </div>
              );
            })}
          </pre>
        </div>
      ))}
    </div>
  );
}
