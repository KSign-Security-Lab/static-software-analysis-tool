"use client";

import dynamic from "next/dynamic";
import { useMemo, useState, type ReactNode } from "react";

import FileTree from "./FileTree";
import FindingDetail from "./FindingDetail";
import FindingList from "./FindingList";
import { countByFile, type Engine, type UiFinding } from "@/lib/model/finding";

const CodeCanvas = dynamic(() => import("./CodeCanvas"), { ssr: false });

/**
 * The layout both analysis pages use: files, code, findings.
 *
 * Sharing it is the point. The two engines run separately and are not being
 * forced together, but a result from either is read the same way -- same
 * markers, same evidence trail, same navigation. Before this the structural
 * side was a tab bar of graphs and the agent side was a different app.
 *
 * `lenses` are extra views over the same selection (the graph explorer, raw
 * JSON). They replace the code pane rather than living somewhere else, because
 * they are ways of looking at the same target.
 */

export interface Lens {
  key: string;
  label: string;
  render: () => ReactNode;
}

export default function Workspace({
  files,
  activeFile,
  fileContent,
  findings,
  onOpenFile,
  lenses = [],
  toolbar,
  status,
}: {
  files: string[];
  activeFile: string | null;
  fileContent: string;
  findings: UiFinding[];
  onOpenFile: (path: string) => void;
  lenses?: Lens[];
  toolbar?: ReactNode;
  status?: ReactNode;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [engines, setEngines] = useState<Set<Engine>>(() => new Set<Engine>(["structural", "agent"]));
  const [lens, setLens] = useState("code");

  const selected = useMemo(() => findings.find((f) => f.id === selectedId) ?? null, [findings, selectedId]);
  const counts = useMemo(() => countByFile(findings), [findings]);

  const openFinding = (finding: UiFinding) => {
    setSelectedId(finding.id);
    setLens("code");
    if (finding.primary.file && finding.primary.file !== activeFile) onOpenFile(finding.primary.file);
  };

  // The line is not needed here: CodeCanvas reveals the selected finding's
  // line itself, so this only has to make sure the right file is open.
  const navigate = (file: string) => {
    setLens("code");
    if (file && file !== activeFile) onOpenFile(file);
  };

  const toggleEngine = (engine: Engine) => {
    setEngines((prev) => {
      const next = new Set(prev);
      if (next.has(engine)) next.delete(engine);
      else next.add(engine);
      return next;
    });
  };

  const active = lenses.find((l) => l.key === lens);

  return (
    <div className="ws">
      {toolbar && <div className="ws-toolbar">{toolbar}</div>}
      {status}

      <div className="ws-grid">
        <aside className="ws-left">
          <div className="ws-pane-title">파일</div>
          <FileTree files={files} selected={activeFile} counts={counts} onSelect={onOpenFile} />
        </aside>

        <section className="ws-center">
          {lenses.length > 0 && (
            <div className="ws-lenses">
              <button
                type="button"
                className={`ws-lens ${lens === "code" ? "is-active" : ""}`}
                onClick={() => setLens("code")}
              >
                코드
              </button>
              {lenses.map((l) => (
                <button
                  key={l.key}
                  type="button"
                  className={`ws-lens ${lens === l.key ? "is-active" : ""}`}
                  onClick={() => setLens(l.key)}
                >
                  {l.label}
                </button>
              ))}
            </div>
          )}
          <div className="ws-canvas">
            {active ? (
              active.render()
            ) : (
              <CodeCanvas
                path={activeFile}
                content={fileContent}
                findings={findings}
                selected={selected}
                onSelect={setSelectedId}
              />
            )}
          </div>
        </section>

        <aside className="ws-right">
          {selected ? (
            <FindingDetail finding={selected} onNavigate={navigate} onClose={() => setSelectedId(null)} />
          ) : (
            <FindingList
              findings={findings}
              selectedId={selectedId}
              engines={engines}
              onToggleEngine={toggleEngine}
              onSelect={openFinding}
            />
          )}
        </aside>
      </div>
    </div>
  );
}
