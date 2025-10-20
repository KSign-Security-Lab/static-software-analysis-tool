"use client";

import React, { useEffect, useId, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import type { OnMount } from "@monaco-editor/react";
import type * as monacoNs from "monaco-editor";
import { FlowType, IDFGEdge, IDFGGraph, IDFGNode } from "@ssat/core/types/dfg";

// Lazy-load Monaco for Next.js (no SSR)
const MonacoEditor = dynamic(async () => (await import("@monaco-editor/react")).default, {
  ssr: false,
});

export interface DFGCodeAnnotatorProps {
  code: string; // full source as a single string
  graph: IDFGGraph; // your provided graph (nodes + edges)
  emphasizeLines?: number[]; // optional highlight lines
  height?: number | string; // default 640
  theme?: "light" | "dark"; // Monaco theme
  className?: string;
  /** Pixel width of the invisible hit area for edge selection */
  hitWidth?: number; // default 14
}

/* =========================================================
   Component (Monaco + edge list + overlay)
   ========================================================= */

/**
 * DFGCodeAnnotator (Monaco)
 * - Monaco for pretty code (read-only).
 * - Right-rail SVG overlay: shows **only the selected edge**.
 * - New: **Edge List** column. Click an item to reveal its connector and details.
 * - Scroll fix: SVG root uses pointerEvents: "none"; only explicit hit-path is clickable.
 * - Crowded edges fix: invisible, thick hit-path (`hitWidth`) improves selection.
 */
export default function DFGCodeAnnotator({
  code,
  graph,
  emphasizeLines = [],
  height = 640,
  theme = "light",
  className,
  hitWidth = 14,
}: DFGCodeAnnotatorProps) {
  const instanceId = useId().replace(/[:]/g, "");
  const editorRef = useRef<monacoNs.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof monacoNs | null>(null);

  const [selectedEdgeIdx, setSelectedEdgeIdx] = useState<number | null>(null);
  const [hoveredEdgeIdx, setHoveredEdgeIdx] = useState<number | null>(null);

  // Nodes lookup
  const nodeById = useMemo(() => {
    const m = new Map<number, IDFGNode>();
    for (const n of graph.nodes) m.set(n.id, n);
    return m;
  }, [graph.nodes]);

  // Edges with numeric line info
  const decoratedEdges = useMemo(() => {
    const toNum = (v: unknown) => {
      if (typeof v === "number") return Number.isFinite(v) ? v : undefined;
      if (typeof v === "string") {
        const n = parseInt(v, 10);
        return Number.isFinite(n) ? n : undefined;
      }
      return undefined;
    };
    const out: Array<{
      edge: IDFGEdge;
      srcLine?: number;
      dstLine?: number;
      sourceNode?: IDFGNode;
      destNode?: IDFGNode;
      idx: number;
    }> = [];
    graph.edges.forEach((edge, idx) => {
      const dbg = (edge.debug || {}) as Record<string, unknown>;
      const srcLine = toNum(dbg["srcLine"]);
      const dstLine = toNum(dbg["dstLine"]);
      out.push({
        edge,
        srcLine,
        dstLine,
        sourceNode: nodeById.get(edge.source),
        destNode: nodeById.get(edge.destination),
        idx,
      });
    });
    return out;
  }, [graph.edges, nodeById]);

  const visibleEdges = useMemo(() => decoratedEdges.filter((e) => Number.isFinite(e.srcLine) && Number.isFinite(e.dstLine)), [decoratedEdges]);

  // Sort for the list: srcLine ASC, then dstLine ASC
  const listEdges = useMemo(() => {
    const copy = [...visibleEdges];
    copy.sort((a, b) => a.srcLine! - b.srcLine! || a.dstLine! - b.dstLine!);
    return copy;
  }, [visibleEdges]);

  // Reveal target line when selecting from the list
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor || selectedEdgeIdx == null) return;
    const hit = visibleEdges.find((e) => e.idx === selectedEdgeIdx);
    if (!hit) return;
    const focusLine = hit.dstLine ?? hit.srcLine!;
    try {
      editor.revealLineInCenter(focusLine);
    } catch {}
  }, [selectedEdgeIdx, visibleEdges]);

  // Monaco mount & listeners
  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor as unknown as monacoNs.editor.IStandaloneCodeEditor;
    monacoRef.current = monaco as unknown as typeof monacoNs;

    editor.updateOptions({
      readOnly: true,
      fontSize: 13,
      fontLigatures: true,
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      automaticLayout: true,
      lineNumbers: "on",
      folding: true,
      glyphMargin: true,
      wordWrap: "off",
    });
  };

  // Language heuristic
  const language = useMemo(() => detectLanguageFromSource(code) || "c", [code]);

  // Decorations: emphasize + selected/hovered
  const decorationsRef = useRef<string[]>([]);
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;

    const decs: monacoNs.editor.IModelDeltaDecoration[] = [];
    for (const ln of emphasizeLines) {
      decs.push({ range: new monaco.Range(ln, 1, ln, 1), options: { isWholeLine: true, className: "dfg-emph-line" } });
    }

    const hit = visibleEdges.find((e) => e.idx === (selectedEdgeIdx ?? -1)) || visibleEdges.find((e) => e.idx === (hoveredEdgeIdx ?? -1));

    if (hit?.srcLine)
      decs.push({ range: new monaco.Range(hit.srcLine, 1, hit.srcLine, 1), options: { isWholeLine: true, className: "dfg-src-line" } });
    if (hit?.dstLine)
      decs.push({ range: new monaco.Range(hit.dstLine, 1, hit.dstLine, 1), options: { isWholeLine: true, className: "dfg-dst-line" } });

    decorationsRef.current = editor.deltaDecorations(decorationsRef.current, decs);
  }, [emphasizeLines, selectedEdgeIdx, hoveredEdgeIdx, visibleEdges]);

  // Layout helpers for overlay
  const layout = (() => {
    const editor = editorRef.current;
    if (!editor) return { contentLeft: 0, contentWidth: 0, width: 0, height: 0 };
    const li = editor.getLayoutInfo();
    const dom = editor.getDomNode();
    return { contentLeft: li.contentLeft, contentWidth: li.contentWidth, width: dom ? dom.clientWidth : 0, height: dom ? dom.clientHeight : 0 };
  })();

  const getLineCenterY = (lineNumber: number): number | null => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return null;
    const top = editor.getTopForLineNumber(lineNumber);
    const lineHeight = editor.getOption(monaco.editor.EditorOption.lineHeight);
    const y = top - editor.getScrollTop() + lineHeight / 2;
    return y;
  };

  // Geometry
  const railWidth = 120; // compact since we show only one edge
  const listWidth = 260; // new edge list column
  const detailsWidth = 288; // details column
  const toolbarHeight = 40;
  const codeRightX = layout.contentLeft + layout.contentWidth;
  const railXStart = codeRightX + 8;

  // Single-edge path (selected only)
  function buildEdgePath(y1: number, y2: number): string {
    const x1 = codeRightX - 8;
    const xRail = railXStart + 8;
    const vMid = y1 + (y2 - y1) / 2;
    return [
      `M ${x1} ${y1}`,
      `L ${xRail - 6} ${y1}`,
      `Q ${xRail} ${y1} ${xRail} ${y1 + 6}`,
      `L ${xRail} ${vMid - 6}`,
      `Q ${xRail} ${vMid} ${xRail + 6} ${vMid}`,
      `L ${xRail + 6} ${vMid}`,
      `Q ${xRail + 12} ${vMid} ${xRail + 12} ${vMid + 6}`,
      `L ${xRail + 12} ${y2 - 6}`,
      `Q ${xRail + 12} ${y2} ${xRail + 18} ${y2}`,
      `L ${x1} ${y2}`,
    ].join(" ");
  }

  const flowToColor: Record<FlowType, string> = {
    [FlowType.BASE]: "#0ea5e9",
    [FlowType.INDEX]: "#6366f1",
    [FlowType.SIZE]: "#10b981",
    [FlowType.VALUE]: "#f59e0b",
  };

  // --- Styles --------------------------------------------------------------
  const containerStyle: React.CSSProperties = {
    width: "100%",
    height: typeof height === "number" ? `${height}px` : height,
    border: "1px solid #e2e8f0",
    borderRadius: 12,
    boxShadow: "0 1px 2px rgba(16,24,40,0.04)",
    overflow: "hidden",
    background: "#fff",
  };
  const toolbarStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "8px 12px",
    borderBottom: "1px solid #e2e8f0",
    height: toolbarHeight,
    boxSizing: "border-box",
  };
  const gridStyle: React.CSSProperties = {
    display: "grid",
    gridTemplateColumns: `1fr 1px ${listWidth}px 1px ${detailsWidth}px`,
    height: `calc(100% - ${toolbarHeight}px)`,
  };
  const editorAreaStyle: React.CSSProperties = { position: "relative", paddingRight: 8 + railWidth, minWidth: 0 };
  const divider: React.CSSProperties = { width: 1, background: "#e2e8f0" };

  return (
    <div className={className} style={containerStyle}>
      {/* Toolbar */}
      <div style={toolbarStyle}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span style={{ fontSize: 13, fontWeight: 600, color: "#334155" }}>DFG Viewer</span>
        </div>
        <div style={{ fontSize: 12, color: "#64748b" }}>{visibleEdges.length} edge(s)</div>
      </div>

      {/* Main layout: editor | list | details */}
      <div style={gridStyle}>
        {/* Editor area */}
        <div style={editorAreaStyle}>
          <MonacoEditor
            value={code}
            language={language}
            theme={theme === "dark" ? "vs-dark" : "vs"}
            onMount={handleMount}
            options={{
              readOnly: true,
              automaticLayout: true,
              glyphMargin: true,
              folding: true,
              scrollBeyondLastLine: false,
              minimap: { enabled: false },
              fontLigatures: true,
              fontSize: 13,
            }}
            loading={<div style={{ padding: 12, fontSize: 13, color: "#64748b" }}>Loading code…</div>}
          />

          {/* Overlay shows only the selected edge */}
          <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", zIndex: 20, pointerEvents: "none" }} aria-hidden>
            <defs>
              <marker id={`arrow-${instanceId}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
              </marker>
            </defs>

            {selectedEdgeIdx != null &&
              (() => {
                const hit = visibleEdges.find((e) => e.idx === selectedEdgeIdx);
                if (!hit || !hit.srcLine || !hit.dstLine) return null;
                const y1 = getLineCenterY(hit.srcLine);
                const y2 = getLineCenterY(hit.dstLine);
                if (y1 == null || y2 == null) return null;
                const d = buildEdgePath(y1, y2);
                const color = flowToColor[hit.edge.features.flow];
                return (
                  <g>
                    <path
                      d={d}
                      fill="none"
                      stroke={color}
                      strokeWidth={2.5}
                      markerEnd={`url(#arrow-${instanceId})`}
                      opacity={0.95}
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      vectorEffect="non-scaling-stroke"
                      style={{ pointerEvents: "none" }}
                    />
                    {/* Hit-path */}
                    <path
                      d={d}
                      fill="none"
                      stroke="transparent"
                      strokeWidth={hitWidth}
                      style={{ pointerEvents: "stroke", cursor: "pointer" }}
                      onMouseEnter={() => setHoveredEdgeIdx(hit.idx)}
                      onMouseLeave={() => setHoveredEdgeIdx((cur) => (cur === hit.idx ? null : cur))}
                      onClick={() => setSelectedEdgeIdx(hit.idx)}
                    />
                  </g>
                );
              })()}
          </svg>
        </div>

        {/* Divider */}
        <div style={divider} />

        {/* Edge list */}
        <aside style={{ overflow: "auto", padding: 8 }}>
          <div style={{ fontSize: 12, color: "#64748b", margin: "4px 0 8px" }}>Edges</div>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {listEdges.map(({ edge, srcLine, dstLine, idx }) => {
              const active = idx === selectedEdgeIdx;
              return (
                <button
                  key={`item-${idx}`}
                  onClick={() => setSelectedEdgeIdx(idx)}
                  style={{
                    textAlign: "left",
                    border: "1px solid #e2e8f0",
                    background: active ? "#eff6ff" : "#fff",
                    color: "#0f172a",
                    borderRadius: 8,
                    padding: "6px 8px",
                    cursor: "pointer",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 12, fontWeight: 600 }}>{edge.features.flow}</span>
                    <span style={{ fontSize: 11, color: "#64748b" }}>{edge.features.guard}</span>
                  </div>
                  <div style={{ fontSize: 11, color: "#475569", marginTop: 2 }}>
                    L{srcLine} → L{dstLine}
                  </div>
                  {typeof (edge.debug as Record<string, unknown>)?.var === "string" ? (
                    <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>var: {String((edge.debug as Record<string, unknown>).var)}</div>
                  ) : null}
                </button>
              );
            })}
          </div>
        </aside>

        {/* Divider */}
        <div style={divider} />

        {/* Details panel */}
        <aside style={{ padding: 12, overflow: "auto", fontSize: 13, color: "#334155" }}>
          {selectedEdgeIdx === null ? (
            <div>
              <div style={{ color: "#64748b", marginBottom: 8 }}>Select an edge from the list.</div>
            </div>
          ) : (
            (() => {
              const hit = visibleEdges.find((e) => e.idx === selectedEdgeIdx)!;
              const { edge, srcLine, dstLine } = hit;
              const dbg = (edge.debug || {}) as Record<string, unknown>;

              const badge = (label: string) => (
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    border: "1px solid #cbd5e1",
                    borderRadius: 999,
                    padding: "2px 8px",
                    fontSize: 12,
                    color: "#334155",
                    marginRight: 6,
                  }}
                >
                  {label}
                </span>
              );

              return (
                <div>
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
                    <h3 style={{ margin: 0, fontSize: 14, color: "#0f172a" }}>Edge</h3>
                    <button
                      onClick={() => setSelectedEdgeIdx(null)}
                      style={{
                        fontSize: 12,
                        padding: "4px 8px",
                        border: "1px solid #cbd5e1",
                        background: "#fff",
                        borderRadius: 6,
                        cursor: "pointer",
                      }}
                    >
                      Clear
                    </button>
                  </div>

                  <div>
                    {badge(`Flow: ${edge.features.flow}`)}
                    {badge(`Guard: ${edge.features.guard}`)}
                    {edge.features.hasLowerGuard ? badge("LowerGuard") : null}
                    {edge.features.hasUpperGuard ? badge("UpperGuard") : null}
                  </div>

                  <div style={{ marginTop: 8, border: "1px solid #e2e8f0", borderRadius: 8 }}>
                    <div style={{ display: "grid", gridTemplateColumns: "100px 1fr", columnGap: 8, rowGap: 4, padding: "8px 12px", fontSize: 12 }}>
                      <div style={{ color: "#64748b" }}>srcLine</div>
                      <div
                        style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace" }}
                      >
                        {srcLine ?? "—"}
                      </div>
                      <div style={{ color: "#64748b" }}>dstLine</div>
                      <div
                        style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace" }}
                      >
                        {dstLine ?? "—"}
                      </div>
                      {typeof dbg["var"] === "string" ? (
                        <>
                          <div style={{ color: "#64748b" }}>var</div>
                          <div
                            style={{
                              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                            }}
                          >
                            {String(dbg["var"])}
                          </div>
                        </>
                      ) : null}
                      {typeof (edge.features.upperGuardNormalization as number | undefined) === "number" ? (
                        <>
                          <div style={{ color: "#64748b" }}>upperGuardNorm</div>
                          <div
                            style={{
                              fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
                            }}
                          >
                            {edge.features.upperGuardNormalization.toFixed(3)}
                          </div>
                        </>
                      ) : null}
                    </div>
                  </div>
                </div>
              );
            })()
          )}
        </aside>
      </div>

      {/* Monaco line decorations */}
      <style jsx global>{`
        .dfg-emph-line {
          background: rgba(250, 204, 21, 0.16);
        }
        .dfg-src-line {
          background: rgba(56, 189, 248, 0.18);
        }
        .dfg-dst-line {
          background: rgba(52, 211, 153, 0.18);
        }
      `}</style>
    </div>
  );
}

/* =========================================================
   Utilities
   ========================================================= */

function detectLanguageFromSource(source: string): string | null {
  const first = source.split(/\n/, 1)[0] || "";
  const lowered = first.toLowerCase();
  if (lowered.includes(".c") || /#include /.test(source)) return "c";
  if (lowered.includes(".cpp") || /#include <.*>/.test(source)) return "cpp";
  if (/^\s*#\!.*\bpython/.test(source) || /def\s+\w+\(/.test(source)) return "python";
  if (/\bclass\s+\w+\s*\{/.test(source) && /public:|private:|protected:/.test(source)) return "cpp";
  if (/\bfunction\s+\w+\(|=>\s*\{/.test(source)) return "javascript";
  return null;
}
