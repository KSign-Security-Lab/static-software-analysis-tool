"use client";

import { useEffect, useMemo, useState } from "react";
import GraphView from "./GraphView";
import NodePanel from "./NodePanel";
import { nonEmptyFunctions, pipelineAstView, pipelineDfgView } from "@/lib/pipeline";
import type { PipelineFunction, PipelineViewKey, ViewNode } from "@/lib/types";

/**
 * Renders the SSAT pipeline's own per-function artifacts.
 *
 * Simpler than GraphExplorer on purpose: these graphs are already scoped to a
 * single function, so there is no method scoping or edge-label layering to do
 * -- pick a function and draw it. Reuses the same <GraphView> renderer, so both
 * kinds of graph look and behave identically.
 */
export default function PipelineExplorer({
  functions,
  tab,
  focusFunction,
}: {
  functions: PipelineFunction[];
  tab: PipelineViewKey;
  focusFunction?: string | null;
}) {
  const usable = useMemo(() => nonEmptyFunctions(functions), [functions]);
  const [selectedName, setSelectedName] = useState<string>("");
  const [selected, setSelected] = useState<ViewNode | null>(null);

  useEffect(() => {
    const wanted =
      focusFunction && usable.some((f) => f.function_name === focusFunction) ? focusFunction : "";
    setSelectedName(wanted || usable[0]?.function_name || "");
    setSelected(null);
  }, [usable, focusFunction, tab]);

  const fn = useMemo(
    () => usable.find((f) => f.function_name === selectedName) ?? usable[0],
    [usable, selectedName],
  );

  const view = useMemo(() => {
    if (!fn) return null;
    return tab === "pipeline-ast" ? pipelineAstView(fn) : pipelineDfgView(fn);
  }, [fn, tab]);

  if (!usable.length) {
    return (
      <div className="empty">
        이 소스에서 파이프라인이 추출한 함수가 없습니다.
        <div className="muted small" style={{ marginTop: 10 }}>
          본문이 있는 함수 정의만 분석하며, 선언과 <code>main</code>은 건너뜁니다.
        </div>
      </div>
    );
  }

  return (
    <div className="explorer">
      <div className="toolbar">
        <label className="tbfield">
          <span>함수</span>
          <select value={selectedName} onChange={(e) => setSelectedName(e.target.value)}>
            {usable.map((f) => (
              <option key={f.function_name} value={f.function_name}>
                {f.function_name}
              </option>
            ))}
          </select>
        </label>
        {view && (
          <span className="muted small tbcount">
            노드 {view.nodes.length}개 · 엣지 {view.edges.length}개
          </span>
        )}
      </div>

      <div className="stage">
        <div className="graph-wrap">
          {view && <div className="view-desc">{view.description}</div>}
          {view && <GraphView view={view} onSelectNode={setSelected} />}
        </div>
        <div>
          <NodePanel node={selected} />
        </div>
      </div>
    </div>
  );
}
