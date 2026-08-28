// Turn a GraphView into positioned React-Flow nodes/edges via a dagre layout.

import dagre from "dagre";
import type { Edge, Node } from "@xyflow/react";
import type { GraphView, ViewKey } from "./types";

const NODE_W = 190;
const NODE_H = 46;

// A colour per Joern vertex label so each view is readable at a glance.
const LABEL_COLORS: Record<string, string> = {
  METHOD: "#6956a8",
  CALL: "#2f5f98",
  IDENTIFIER: "#0f766e",
  LITERAL: "#c8641a",
  FIELD_IDENTIFIER: "#3f8f2f",
  CONTROL_STRUCTURE: "#b8791a",
  METHOD_PARAMETER_IN: "#4a6b6b",
  LOCAL: "#4a6b6b",
  RETURN: "#7a5a3a",
  BLOCK: "#5f676e",
};

export function labelColor(label: string): string {
  return LABEL_COLORS[label] ?? "#556070";
}

const DIRECTION: Record<ViewKey, "TB" | "LR"> = {
  cpg: "LR",
  ast: "TB",
  cg: "LR",
  dfg: "LR",
  cfg: "TB",
  "pipeline-ast": "TB",
  "pipeline-dfg": "LR",
};

export interface NodeData extends Record<string, unknown> {
  label: string;
  cpgLabel: string;
  name: string;
  code: string;
  line: string | number;
}

export interface LaidOut {
  nodes: Node<NodeData>[];
  edges: Edge[];
}

function shortText(view: GraphView): (id: string) => { title: string; sub: string; cpgLabel: string } {
  const map = new Map(view.nodes.map((n) => [n.id, n]));
  return (id: string) => {
    const n = map.get(id);
    if (!n) return { title: id, sub: "", cpgLabel: "" };
    const primary = n.name || n.code || n.label;
    const title = primary.length > 26 ? primary.slice(0, 25) + "…" : primary;
    return { title, sub: n.label, cpgLabel: n.label };
  };
}

export function layoutView(view: GraphView): LaidOut {
  const dir = DIRECTION[view.key];
  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: dir, nodesep: 36, ranksep: 64, marginx: 20, marginy: 20 });

  const present = new Set(view.nodes.map((n) => n.id));
  view.nodes.forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  const edges = view.edges.filter((e) => present.has(e.source) && present.has(e.target));
  edges.forEach((e) => g.setEdge(e.source, e.target));

  dagre.layout(g);

  const text = shortText(view);
  const nodes: Node<NodeData>[] = view.nodes.map((n) => {
    const p = g.node(n.id);
    const t = text(n.id);
    const color = labelColor(n.label);
    return {
      id: n.id,
      position: { x: (p?.x ?? 0) - NODE_W / 2, y: (p?.y ?? 0) - NODE_H / 2 },
      data: { label: t.title, cpgLabel: n.label, name: n.name, code: n.code, line: n.line },
      style: {
        width: NODE_W,
        borderRadius: 10,
        border: `2px solid ${color}`,
        background: "var(--node-bg)",
        color: "var(--fg)",
        fontSize: 12,
        padding: "6px 8px",
      },
    };
  });

  const flowEdges: Edge[] = edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    label: e.label || undefined,
    animated: view.key === "dfg",
    style: { stroke: "#9aa0aa", strokeWidth: 1.5 },
    labelStyle: { fill: "#c8641a", fontSize: 10 },
  }));

  return { nodes, edges: flowEdges };
}
