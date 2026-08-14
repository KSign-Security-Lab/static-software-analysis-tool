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
   * Drawn in accent, and everything else dims. Dimming alone was the rule while
   * a node carried five states on one box and a sixth colour would have been a
   * legend nobody can hold -- but the states live on a puck's ring now, so the
   * path can have the colour, and it needs it: at 45% against 100% the
   * difference is only visible to someone already looking for it.
   *
   * Safe to reuse the accent that marks a running node, because the two never
   * co-occur: a trail is read from a finished finding, and `running` exists only
   * mid-run.
   */
  path?: readonly string[] | null;
  /**
   * Bump to re-fit the canvas.
   *
   * A number rather than a ref handle, because `fitView` comes from a hook that
   * only works inside the provider this component owns -- so a caller outside it
   * cannot hold the handle, and hoisting the provider to reach it is what the
   * old studio did and what broke lazy loading.
   */
  fit?: number;
  /** Draw the five specialists separately instead of as one node. */
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
        // The trail names real nodes. Collapsed, the specialist it names is not
        // on the canvas under its own id, so the group is handed the name and
        // says it instead -- which is the answer the reader came for.
        litLenses: path ? [...path] : [],
      }),
    [shape, stats, running, queued, breakpoints, interrupt, direction, expanded, path],
  );

  // The trail names the specialists individually, and collapsed they are drawn
  // as one node that is on no trail by name. Without this the accent path breaks
  // in the middle of the pipeline, at exactly the node that did the finding.
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
      // Only the nodes that *could* have been involved are dimmed. Five of these
      // call no model -- `plan`, `context`, `skip`, `locate`, `reduce` -- so they
      // leave no calls behind and would fall outside every path, and dimming them
      // would say they sat this one out when in fact they run every time. "Which
      // agent was involved" is a question about agents.
      //
      // `lit` is not so restricted: a deterministic node *on* the path is on it,
      // and the trail should read as one continuous line rather than break at
      // `locate` every time.
      data: onPath
        ? {
            ...node.data,
            lit: onPath.has(node.id),
            faded: node.data.steps.length > 0 && !onPath.has(node.id),
          }
        : node.data,
    }));
  }, [laid.nodes, selected, onPath]);

  // An edge is on the trail when both its ends are -- which is what makes the
  // path a line you can follow rather than a scatter of lit nodes. The loop is
  // excluded: `reduce -> plan` closes a wave, and lighting it would draw the
  // reader back to the start of an argument that ended at `verify`.
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

  /**
   * Whether the box this draws into has a size yet.
   *
   * React Flow measures its container on mount and refuses to lay anything out
   * without one -- "[React Flow]: The parent container needs a width and a
   * height to render the graph", error #004, and an empty canvas.
   *
   * It has no size on the first paint here. The chain above is `PanelShell`'s
   * body, which is `min-h-0 flex-1` and so has no *definite* height until flex
   * has resolved it, and a percentage height on a child of that resolves against
   * nothing. Inside a dialog that mounts on open, the first measurement is 0x0.
   *
   * So the canvas waits to be measured rather than assuming. The wrapper is
   * `absolute inset-0` for the same reason -- it takes its size from a
   * positioned ancestor rather than from a percentage of an indefinite one, so
   * once the panel has any size at all this has exactly that size.
   */
  const [sized, setSized] = useState(false);

  // Refit on a change of shape or direction, and whenever the pane is resized --
  // not when a node lights up, which would yank the canvas about while somebody
  // is reading it.
  //
  // The resize half is the one that matters here. This is a nine-rank pipeline
  // about 1800px wide, and the bottom panel is roughly 900: it fits at 0.48,
  // which puts the node labels at five pixels. Dragging the panel taller was the
  // obvious response and did nothing, because `fitView` only ran on mount -- so
  // the reader made room and got the same unreadable drawing in more of it.
  // Watching the box is separate from refitting it, because it has to run before
  // the canvas exists -- that is the whole point of `sized`.
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
    // 0.08 was 8% of the zoom given away to margin, back when the drawing was
    // being fitted into a pane where every percent mattered and it still came
    // out at 0.3. The canvas has room now and the layout carries its own margin.
    const refit = () => fitView({ padding: 0.04, duration: 0 });
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
  }, [fitView, shape, direction, fit, sized]);

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    if (TERMINALS.has(node.id)) return;
    // The group is not a node, so there is nothing to select and nothing for the
    // panel to describe. Opening it is the only thing it can usefully do, and it
    // is what a stack of five asks to be clicked for.
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
      // The 0.3 floor existed to make an impossible box survivable: the drawing
      // was fitted into 460x334 and came out at exactly that, with 37x19 nodes.
      // It fits near 0.9 in the canvas it has now, so the floor can stop being a
      // place the graph actually lands.
      minZoom={0.5}
      maxZoom={1.8}
      fitView
      // React Flow themes itself through these, which is both documented and
      // more robust than reaching into its class names with arbitrary
      // variants -- those need escaping and break silently when it renames one.
      style={{ ...FLOW_THEME, ...FLOW_EDGE_THEME }}
    >
      <FlowChrome />
    </ReactFlow>
    )}
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
