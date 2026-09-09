"use client";

import { Background, BackgroundVariant, Controls } from "@xyflow/react";

export const FLOW_THEME = {
  "--xy-background-color": "transparent",
  "--xy-controls-button-background-color": "var(--surface-2)",
  "--xy-controls-button-background-color-hover": "var(--surface-3)",
  "--xy-controls-button-color": "var(--ink-muted)",
  "--xy-controls-button-color-hover": "var(--ink)",
  "--xy-controls-button-border-color": "var(--line)",
} as React.CSSProperties;

export const FLOW_EDGE_THEME = {
  "--xy-edge-stroke": "var(--line-3)",
  "--xy-edge-stroke-selected": "var(--accent)",
} as React.CSSProperties;

export default function FlowChrome() {
  return (
    <>
      <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--line-2)" />
      <Controls showInteractive={false} position="bottom-left" className="!shadow-none" />
    </>
  );
}
