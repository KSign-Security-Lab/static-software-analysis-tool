"use client";

import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type NodeMouseHandler,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef } from "react";

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
  /**
   * The nodes that produced the finding being read, if one is.
   *
   * Everything else dims. Dimming rather than highlighting because a node
   * already carries five states -- visited, queued, running, breakpointed,
   * selected -- and a sixth colour competing with those would be a legend nobody
   * can hold. Taking light away from the irrelevant ones leaves all five intact
   * on the ones that matter.
   */
  path?: readonly string[] | null;
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
  path,
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

  const nodes = useMemo(() => {
    const onPath = path ? new Set(path) : null;
    return laid.nodes.map((node) => ({
      ...node,
      selected: node.id === selected,
      // Only the nodes that *could* have been involved are dimmed. Five of these
      // call no model -- `plan`, `context`, `skip`, `locate`, `reduce` -- so they
      // leave no calls behind and would fall outside every path, and dimming them
      // would say they sat this one out when in fact they run every time. "Which
      // agent was involved" is a question about agents.
      data:
        onPath && node.data.steps.length > 0
          ? { ...node.data, faded: !onPath.has(node.id) }
          : node.data,
    }));
  }, [laid.nodes, selected, path]);

  const { fitView } = useReactFlow();
  const wrapper = useRef<HTMLDivElement | null>(null);

  // Refit on a change of shape or direction, and whenever the pane is resized --
  // not when a node lights up, which would yank the canvas about while somebody
  // is reading it.
  //
  // The resize half is the one that matters here. This is a nine-rank pipeline
  // about 1800px wide, and the bottom panel is roughly 900: it fits at 0.48,
  // which puts the node labels at five pixels. Dragging the panel taller was the
  // obvious response and did nothing, because `fitView` only ran on mount -- so
  // the reader made room and got the same unreadable drawing in more of it.
  useEffect(() => {
    const refit = () => fitView({ padding: 0.08, duration: 0 });
    refit();

    const element = wrapper.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      // One refit per frame: a drag fires this continuously, and `fitView` reads
      // layout, so doing it per event is a reflow per pixel of the drag.
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(refit);
    });
    observer.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [fitView, shape, direction]);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    if (TERMINALS.has(node.id)) return;
    onSelect(node.id === selected ? null : node.id);
  };

  return (
    <div ref={wrapper} className="h-full w-full">
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
    </div>
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
