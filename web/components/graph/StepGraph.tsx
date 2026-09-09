"use client";

import {
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type NodeMouseHandler,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { Breakpoints } from "@/lib/api/control";
import type { GraphShape, TraceSpan } from "@/lib/api/types";
import { LENS_GROUP, TERMINALS, layoutGraph, statsFromSpans } from "@/lib/trace/layout";
import FlowChrome, { FLOW_EDGE_THEME, FLOW_THEME } from "./chrome";
import RoutedEdge from "./RoutedEdge";
import StepNode from "./StepNode";

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
  path?: readonly string[] | null;
  fit?: number;
  expanded?: boolean;
  onExpand?: (next: boolean) => void;
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
  fit = 0,
  expanded = false,
  onExpand,
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
        expanded,
        litLenses: path ? [...path] : [],
      }),
    [shape, stats, running, queued, breakpoints, interrupt, direction, expanded, path],
  );

  const onPath = useMemo(() => {
    if (!path) return null;
    const set = new Set(path);
    if (laid.lenses.some((each) => set.has(each))) set.add(LENS_GROUP);
    return set;
  }, [path, laid.lenses]);

  const nodes = useMemo(() => {
    return laid.nodes.map((node) => ({
      ...node,
      selected: node.id === selected,
      data: onPath
        ? {
            ...node.data,
            lit: onPath.has(node.id),
            faded: node.data.steps.length > 0 && !onPath.has(node.id),
          }
        : node.data,
    }));
  }, [laid.nodes, selected, onPath]);

  const edges = useMemo(() => {
    if (!onPath) return laid.edges;
    return laid.edges.map((edge) =>
      onPath.has(edge.source) && onPath.has(edge.target) && !edge.className?.includes("is-loop")
        ? { ...edge, data: { ...edge.data, lit: true } }
        : edge,
    );
  }, [laid.edges, onPath]);

  const { fitView } = useReactFlow();
  const wrapper = useRef<HTMLDivElement | null>(null);

  const [sized, setSized] = useState(false);

  useEffect(() => {
    const element = wrapper.current;
    if (!element) return;
    const measure = () => {
      const { width, height } = element.getBoundingClientRect();
      setSized(width > 0 && height > 0);
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!sized) return;
    const refit = () => fitView({ padding: 0.04, duration: 0 });
    refit();

    const element = wrapper.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    let frame = 0;
    const observer = new ResizeObserver(() => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(refit);
    });
    observer.observe(element);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [fitView, shape, direction, fit, sized]);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    if (TERMINALS.has(node.id)) return;
    if (node.id === LENS_GROUP) {
      onExpand?.(true);
      return;
    }
    onSelect(node.id === selected ? null : node.id);
  };

  return (
    <div ref={wrapper} className="absolute inset-0">
    {sized && (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={NODE_TYPES}
      edgeTypes={EDGE_TYPES}
      onNodeClick={onNodeClick}
      onPaneClick={() => onSelect(null)}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
      minZoom={0.5}
      maxZoom={1.8}
      fitView
      style={{ ...FLOW_THEME, ...FLOW_EDGE_THEME }}
    >
      <FlowChrome />
    </ReactFlow>
    )}
    </div>
  );
}

export default function StepGraph(props: StepGraphProps) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}
