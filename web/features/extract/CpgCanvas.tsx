"use client";

import { Background, BackgroundVariant, Controls, ReactFlow, ReactFlowProvider, type NodeMouseHandler } from "@xyflow/react";
import { useMemo } from "react";

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
      style={
        {
          "--xy-background-color": "transparent",
          "--xy-controls-button-background-color": "var(--surface-2)",
          "--xy-controls-button-background-color-hover": "var(--surface-3)",
          "--xy-controls-button-color": "var(--ink-muted)",
          "--xy-controls-button-color-hover": "var(--ink)",
          "--xy-controls-button-border-color": "var(--line)",
        } as React.CSSProperties
      }
    >
      <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--line-2)" />
      <Controls showInteractive={false} position="bottom-left" className="!shadow-none" />
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
