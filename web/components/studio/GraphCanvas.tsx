"use client";

import { useCallback, useEffect, useMemo } from "react";
import { Background, BackgroundVariant, Controls, ReactFlow, useReactFlow, type NodeMouseHandler } from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import GraphNode from "./GraphNode";
import type { Breakpoints, GraphShape, Span } from "@/lib/api/studio";
import { layoutGraph, statsFromSpans, TERMINALS } from "@/lib/studio/layout";

// Defined once at module scope: React Flow warns, loudly and correctly, when
// this object changes identity between renders.
const NODE_TYPES = { studioNode: GraphNode };

/**
 * The graph, with this run drawn onto it.
 *
 * The shape is fixed; the rest comes from the run -- which node is executing,
 * which have been entered and how often, and where it will stop. Interrupts are
 * set on the node itself rather than in a list elsewhere.
 */
export default function GraphCanvas({
  shape,
  spans,
  running,
  queued,
  breakpoints,
  selected,
  onSelect,
  onInterrupt,
  direction = "TB",
}: {
  shape: GraphShape;
  spans: Span[];
  running: string[];
  queued: string[];
  breakpoints: Breakpoints;
  selected: string | null;
  onSelect: (node: string | null) => void;
  onInterrupt: (node: string, when: "before" | "after") => void;
  direction?: "LR" | "TB";
}) {
  const stats = useMemo(() => statsFromSpans(spans), [spans]);

  // Stable, so the node data does not change identity every render.
  const interrupt = useCallback(
    (node: string, when: "before" | "after") => onInterrupt(node, when),
    [onInterrupt],
  );

  const laid = useMemo(
    () =>
      layoutGraph(shape, {
        stats,
        running,
        queued,
        before: breakpoints.before,
        after: breakpoints.after,
        onInterrupt: interrupt,
        direction,
      }),
    [shape, stats, running, queued, breakpoints, interrupt, direction],
  );

  const nodes = useMemo(
    () => laid.nodes.map((node) => ({ ...node, selected: node.id === selected })),
    [laid.nodes, selected],
  );

  const { fitView } = useReactFlow();
  // Only on a change of shape or direction: refitting when a node lights up
  // would yank the canvas about while someone is reading it.
  useEffect(() => {
    // The whole shape, every time. Eleven nodes across do get fitted small,
    // which is why the labels are sized to survive it -- seeing the structure
    // is the point, and the controls are there when a node needs reading.
    fitView({ padding: 0.06, duration: 0 });
  }, [fitView, shape, direction]);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    if (TERMINALS.has(node.id)) return;
    onSelect(node.id === selected ? null : node.id);
  };

  return (
    <ReactFlow
      nodes={nodes}
      edges={laid.edges}
      nodeTypes={NODE_TYPES}
      onNodeClick={onNodeClick}
      onPaneClick={() => onSelect(null)}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
      minZoom={0.3}
      maxZoom={1.8}
      fitView
    >
      <Background variant={BackgroundVariant.Dots} gap={16} size={1} className="gx-bg" />
      <Controls showInteractive={false} position="bottom-left" />
    </ReactFlow>
  );
}
