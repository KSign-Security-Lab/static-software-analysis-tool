"use client";

import { BaseEdge, getSmoothStepPath, type Edge, type EdgeProps } from "@xyflow/react";

import { roundedPath } from "@/lib/trace/edge-path";
import type { RoutedEdgeData } from "@/lib/trace/layout";

/**
 * An edge drawn along the route dagre computed for it.
 *
 * dagre routes while it lays out -- a dummy node per rank an edge crosses, and the
 * points it returns are a path through the gaps between the real nodes. Those
 * points are in the same coordinate space the nodes are positioned in, so they can
 * be drawn directly.
 *
 * The alternative, and what was here, is `smoothstep` between two fixed handles: a
 * path that knows where its ends are and nothing about what lies between them. It
 * put both rank-skipping edges in one lane, on top of each other.
 *
 * Falls back to a step path if a route is missing, so an edge is never simply
 * absent from the drawing.
 */
export default function RoutedEdge({
  data,
  markerEnd,
  style,
  interactionWidth,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
}: EdgeProps<Edge<RoutedEdgeData>>) {
  const points = data?.points;
  const path =
    points && points.length > 1
      ? roundedPath(points)
      : getSmoothStepPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition })[0];

  return <BaseEdge path={path} markerEnd={markerEnd} style={style} interactionWidth={interactionWidth} />;
}
