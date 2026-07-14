"use client";

import { useEffect, useMemo, useState } from "react";
import GraphView from "./GraphView";
import NodePanel from "./NodePanel";
import {
  contract,
  internalMethods,
  isNoise,
  neighborhood,
  scopeCallGraph,
  scopeToMethod,
  searchNodes,
} from "@/lib/graphops";
import { EDGE_TABS, buildViewFromLabels, cgView } from "@/lib/views";
import type { ParsedCpg, ViewKey, ViewNode } from "@/lib/types";

export default function GraphExplorer({
  cpg,
  tab,
  defaultMethodId,
}: {
  cpg: ParsedCpg;
  tab: ViewKey;
  defaultMethodId?: string;
}) {
  const methods = useMemo(() => internalMethods(cpg), [cpg]);
  const isCg = tab === "cg";

  const [methodId, setMethodId] = useState<string>("");
  const [simplify, setSimplify] = useState(true);
  const [labels, setLabels] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [focus, setFocus] = useState<ViewNode | null>(null);
  const [selected, setSelected] = useState<ViewNode | null>(null);

  // Reset controls when the tab (or CPG) changes.
  useEffect(() => {
    setMethodId(defaultMethodId && methods.some((m) => m.id === defaultMethodId) ? defaultMethodId : "");
    setFocus(null);
    setSelected(null);
    setQuery("");
    if (!isCg) {
      const cand = EDGE_TABS[tab as Exclude<ViewKey, "cg">];
      setLabels(new Set(cand.filter((c) => c.on).map((c) => c.label)));
    }
  }, [tab, defaultMethodId, methods, isCg]);

  const view = useMemo(() => {
    // 1. base view (edge layers)
    let v = isCg ? cgView(cpg) : buildViewFromLabels(cpg, tab, [...labels]);
    // 2. scope to a function
    if (methodId) v = isCg ? scopeCallGraph(v, methodId) : scopeToMethod(v, cpg, methodId);
    // 3. collapse noise
    if (simplify && !isCg) v = contract(v, (n) => !isNoise(n));
    // 4. focus a node's neighbourhood
    if (focus && v.nodes.some((n) => n.id === focus.id)) v = neighborhood(v, focus.id, 2);
    return v;
  }, [cpg, tab, isCg, labels, methodId, simplify, focus]);

  const highlight = useMemo(() => searchNodes(view, query), [view, query]);

  const onSelect = (n: ViewNode | null) => {
    setSelected(n);
  };

  const candidates = isCg ? [] : EDGE_TABS[tab as Exclude<ViewKey, "cg">];

  return (
    <div className="explorer">
      <div className="toolbar">
        <label className="tbfield">
          <span>함수</span>
          <select value={methodId} onChange={(e) => setMethodId(e.target.value)}>
            <option value="">{isCg ? "전체 프로그램" : "— 모든 함수 —"}</option>
            {methods.map((m) => (
              <option key={m.id} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
        </label>

        {!isCg && (
          <label className="tbcheck">
            <input type="checkbox" checked={simplify} onChange={(e) => setSimplify(e.target.checked)} />
            <span>단순화 (연산자/리터럴 접기)</span>
          </label>
        )}

        {candidates.length > 1 && (
          <div className="tbedges">
            <span className="muted small">엣지:</span>
            {candidates.map((c) => (
              <label key={c.label} className="tbtoggle">
                <input
                  type="checkbox"
                  checked={labels.has(c.label)}
                  onChange={(e) => {
                    setLabels((prev) => {
                      const next = new Set(prev);
                      if (e.target.checked) next.add(c.label);
                      else next.delete(c.label);
                      return next;
                    });
                  }}
                />
                {c.label}
              </label>
            ))}
          </div>
        )}

        <input
          type="text"
          className="tbsearch"
          placeholder="노드 검색…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />

        {focus && (
          <button className="tbbtn" onClick={() => setFocus(null)}>
            포커스 해제 ✕
          </button>
        )}
        <span className="muted small tbcount">
          노드 {view.nodes.length}개 · 엣지 {view.edges.length}개
        </span>
      </div>

      <div className="stage">
        <div className="graph-wrap">
          <div className="view-desc">{view.description}</div>
          <GraphView view={view} onSelectNode={onSelect} highlight={highlight} />
        </div>
        <div>
          <NodePanel node={selected} />
          {selected && (
            <div style={{ padding: "0 16px 16px" }}>
              <button
                className="tbbtn"
                onClick={() => setFocus(focus?.id === selected.id ? null : selected)}
              >
                {focus?.id === selected.id ? "집중 해제" : "2-홉 이웃에 집중"}
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
