"use client";

import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type NodeMouseHandler,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo } from "react";

import type { Breakpoints } from "@/lib/api/control";
import type { GraphShape, TraceSpan } from "@/lib/api/types";
import { TERMINALS, layoutGraph, statsFromSpans } from "@/lib/trace/layout";
import FlowChrome, { FLOW_EDGE_THEME, FLOW_THEME } from "./chrome";
import RoutedEdge from "./RoutedEdge";
import StepNode from "./StepNode";

// Module scope: React Flow warns, loudly and correctly, when these objects
// change identity between renders.
const NODE_TYPES = { studioNode: StepNode };
const EDGE_TYPES = { routed: RoutedEdge };

export interface StepGraphProps {
  shape: GraphShape;
  spans: TraceSpan[];
  running: string[];
  queued: string[];
  breakpoints: Breakpoints;
  selected: string | null;
  onSelect: (node: string | null) => void;
  onInterrupt: (node: string, when: "before" | "after") => void;
  direction?: "LR" | "TB";
}

function Canvas({
  shape,
  spans,
  running,
  queued,
  breakpoints,
  selected,
  onSelect,
  onInterrupt,
  direction = "LR",
}: StepGraphProps) {
  const stats = useMemo(() => statsFromSpans(spans), [spans]);

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
  // Only on a change of shape or direction. Refitting when a node lights up
  // would yank the canvas about while somebody is reading it.
  useEffect(() => {
    fitView({ padding: 0.08, duration: 0 });
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
      edgeTypes={EDGE_TYPES}
      onNodeClick={onNodeClick}
      onPaneClick={() => onSelect(null)}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
      minZoom={0.3}
      maxZoom={1.8}
      fitView
      // React Flow themes itself through these, which is both documented and
      // more robust than reaching into its class names with arbitrary
      // variants -- those need escaping and break silently when it renames one.
      style={{ ...FLOW_THEME, ...FLOW_EDGE_THEME }}
    >
      <FlowChrome />
    </ReactFlow>
  );
}

/**
 * The agent's graph, with this run drawn onto it.
 *
 * The shape is fixed; the rest comes from the run -- which node is executing,
 * which have been entered and how often, and where it will stop.
 *
 * The provider lives here rather than at the page, because it is an
 * implementation detail of the canvas. Hoisting it, as the old studio did,
 * lets the provider render before its consumer's chunk has arrived.
 */
export default function StepGraph(props: StepGraphProps) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}
