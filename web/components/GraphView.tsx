"use client";

import { useMemo } from "react";
import {
  Background,
  Controls,
  type Edge,
  MiniMap,
  type Node,
  type NodeMouseHandler,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { layoutView, type NodeData } from "@/lib/layout";
import type { GraphView as GraphViewT, ViewNode } from "@/lib/types";

export default function GraphView({
  view,
  onSelectNode,
  highlight,
}: {
  view: GraphViewT;
  onSelectNode: (node: ViewNode | null) => void;
  highlight?: Set<string>;
}) {
  const base = useMemo(() => layoutView(view), [view]);
  const nodeById = useMemo(() => new Map(view.nodes.map((n) => [n.id, n])), [view]);

  const nodes = useMemo(() => {
    if (!highlight || highlight.size === 0) return base.nodes;
    return base.nodes.map((n) => {
      const on = highlight.has(n.id);
      return {
        ...n,
        style: {
          ...n.style,
          opacity: on ? 1 : 0.18,
          boxShadow: on ? "0 0 0 3px rgba(20,184,166,0.7)" : undefined,
        },
      };
    });
  }, [base.nodes, highlight]);

  const onNodeClick: NodeMouseHandler = (_e, node) => {
    onSelectNode(nodeById.get(node.id) ?? null);
  };

  if (view.nodes.length === 0) {
    return (
      <div className="empty">
        표시할 <b>{view.title}</b> 노드가 없습니다.
        <br />
        다른 함수를 고르거나, 단순화를 끄거나, 엣지 레이어를 더 켜 보세요.
      </div>
    );
  }

  return (
    <ReactFlow
      nodes={nodes as Node<NodeData>[]}
      edges={base.edges as Edge[]}
      onNodeClick={onNodeClick}
      onPaneClick={() => onSelectNode(null)}
      fitView
      minZoom={0.05}
      maxZoom={2.5}
      proOptions={{ hideAttribution: true }}
      nodesDraggable
      nodesConnectable={false}
      elementsSelectable
    >
      <Background color="#2a343a" gap={22} />
      <MiniMap
        pannable
        zoomable
        nodeColor={() => "#2f5f98"}
        maskColor="rgba(15,20,23,0.7)"
        style={{ background: "#10161a" }}
      />
      <Controls />
    </ReactFlow>
  );
}
