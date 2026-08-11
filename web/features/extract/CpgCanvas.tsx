"use client";

import { ReactFlow, ReactFlowProvider, type NodeMouseHandler } from "@xyflow/react";
import { useMemo } from "react";

import FlowChrome, { FLOW_THEME } from "@/components/graph/chrome";
import { layoutView } from "@/lib/layout";
import type { GraphView } from "@/lib/types";

/** One projected view of the CPG, laid out and drawn. */
function Canvas({
  view,
  selected,
  onSelect,
}: {
  view: GraphView;
  selected: string | null;
  onSelect: (id: string | null) => void;
}) {
  const laid = useMemo(() => layoutView(view), [view]);

  const nodes = useMemo(
    () => laid.nodes.map((node) => ({ ...node, selected: node.id === selected })),
    [laid.nodes, selected],
  );

  const onNodeClick: NodeMouseHandler = (_event, node) => onSelect(node.id === selected ? null : node.id);

  return (
    <ReactFlow
      nodes={nodes}
      edges={laid.edges}
      onNodeClick={onNodeClick}
      onPaneClick={() => onSelect(null)}
      proOptions={{ hideAttribution: true }}
      nodesConnectable={false}
      minZoom={0.1}
      maxZoom={2}
      fitView
      style={FLOW_THEME}
    >
      <FlowChrome />
    </ReactFlow>
  );
}

export default function CpgCanvas(props: Parameters<typeof Canvas>[0]) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}
