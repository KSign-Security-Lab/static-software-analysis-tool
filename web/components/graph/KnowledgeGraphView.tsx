"use client";

import { ReactFlow, ReactFlowProvider, type NodeMouseHandler } from "@xyflow/react";
import { useMemo } from "react";

import type { KnowledgeGraph } from "@/lib/api/types";
import type { FileCount } from "@/lib/model/finding";
import { layoutKnowledge } from "@/lib/trace/knowledge-layout";
import FlowChrome, { FLOW_THEME } from "./chrome";
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
      style={FLOW_THEME}
    >
      <FlowChrome />
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
