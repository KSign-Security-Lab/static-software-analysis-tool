"use client";

import { Background, BackgroundVariant, Controls, ReactFlow, ReactFlowProvider, type NodeMouseHandler } from "@xyflow/react";
import { useMemo } from "react";

import type { KnowledgeGraph } from "@/lib/api/types";
import type { FileCount } from "@/lib/model/finding";
import { layoutKnowledge } from "@/lib/trace/knowledge-layout";
import KnowledgeNode from "./KnowledgeNode";

const NODE_TYPES = { knowledgeNode: KnowledgeNode };

export interface KnowledgeGraphViewProps {
  graph: KnowledgeGraph;
  counts: Map<string, FileCount>;
  pending: Set<string>;
  running: Set<string>;
  selected: string | null;
  expanded: Set<number>;
  onSelect: (id: string | null) => void;
  onExpand: (community: number) => void;
}

function Canvas({ graph, counts, pending, running, selected, expanded, onSelect, onExpand }: KnowledgeGraphViewProps) {
  const laid = useMemo(
    () => layoutKnowledge(graph, { counts, pending, running, selected, expanded }),
    [graph, counts, pending, running, selected, expanded],
  );

  const onNodeClick: NodeMouseHandler = (_event, node) => {
    if (node.id.startsWith("c") && (node.data as { kind?: string }).kind === "community") {
      onExpand(Number(node.id.slice(1)));
      return;
    }
    onSelect(node.id === selected ? null : node.id);
  };

  return (
    <ReactFlow
      nodes={laid.nodes}
      edges={laid.edges}
      nodeTypes={NODE_TYPES}
      onNodeClick={onNodeClick}
      onPaneClick={() => onSelect(null)}
      proOptions={{ hideAttribution: true }}
      nodesDraggable={false}
      nodesConnectable={false}
      minZoom={0.2}
      maxZoom={1.6}
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

export default function KnowledgeGraphView(props: KnowledgeGraphViewProps) {
  return (
    <ReactFlowProvider>
      <Canvas {...props} />
    </ReactFlowProvider>
  );
}
