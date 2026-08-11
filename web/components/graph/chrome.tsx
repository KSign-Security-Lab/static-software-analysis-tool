"use client";

import { Background, BackgroundVariant, Controls } from "@xyflow/react";

/**
 * The parts every graph canvas draws the same way.
 *
 * Three canvases -- the knowledge graph, the pipeline step graph and the CPG
 * view -- each repeated this theme block and this pair of children verbatim. A
 * dotted grid and bottom-left controls are not something any one of them
 * decides, so they are decided once here.
 */

/**
 * React Flow reads its palette from CSS variables, so the theme is passed as
 * inline custom properties rather than classes. Spread into a canvas `style`.
 */
export const FLOW_THEME = {
  "--xy-background-color": "transparent",
  "--xy-controls-button-background-color": "var(--surface-2)",
  "--xy-controls-button-background-color-hover": "var(--surface-3)",
  "--xy-controls-button-color": "var(--ink-muted)",
  "--xy-controls-button-color-hover": "var(--ink)",
  "--xy-controls-button-border-color": "var(--line)",
} as React.CSSProperties;

/** Edge colours, for the canvases that draw edges you can select. */
export const FLOW_EDGE_THEME = {
  "--xy-edge-stroke": "var(--line-3)",
  "--xy-edge-stroke-selected": "var(--accent)",
} as React.CSSProperties;

/** The dotted grid and the zoom controls, as every canvas wants them. */
export default function FlowChrome() {
  return (
    <>
      <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="var(--line-2)" />
      <Controls showInteractive={false} position="bottom-left" className="!shadow-none" />
    </>
  );
}
