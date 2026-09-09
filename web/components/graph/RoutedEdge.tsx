"use client";

import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type Edge, type EdgeProps } from "@xyflow/react";

import { roundedPath } from "@/lib/trace/edge-path";
import type { RoutedEdgeData } from "@/lib/trace/layout";
import { cn } from "@/lib/utils";

function midpoint(points: { x: number; y: number }[]): { x: number; y: number } {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) total += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);

  let walked = 0;
  for (let i = 1; i < points.length; i += 1) {
    const span = Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);
    if (walked + span >= total / 2) {
      const into = span === 0 ? 0 : (total / 2 - walked) / span;
      return {
        x: points[i - 1].x + (points[i].x - points[i - 1].x) * into,
        y: points[i - 1].y + (points[i].y - points[i - 1].y) * into,
      };
    }
    walked += span;
  }
  return points[points.length - 1];
}

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
  const routed = points && points.length > 1;
  const [stepPath, stepX, stepY] = getSmoothStepPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const lit = data?.lit ?? false;
  const loop = data?.tone === "loop";

  const path = routed ? roundedPath(points) : stepPath;
  const at = routed ? midpoint(points) : loop ? { x: sourceX, y: sourceY } : { x: stepX, y: stepY };

  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        interactionWidth={interactionWidth}
        style={{
          ...style,
          ...(lit ? { stroke: "var(--accent)", strokeWidth: 1.75 } : {}),
        }}
      />

      {data?.label && (
        <EdgeLabelRenderer>
          <div
            className={cn(
              "pointer-events-none absolute rounded-full border px-1.5 py-px font-mono text-2xs leading-tight",
              "border-line-2 bg-surface text-ink-faint",
              loop && "border-alt/40 text-alt",
              lit && "border-accent/50 text-accent-ink",
            )}
            style={{
              transform: loop
                ? `translate(8px, -50%) translate(${at.x}px, ${at.y}px)`
                : data?.across
                  ? `translate(-50%, -50%) translate(${at.x}px, ${at.y - 15}px)`
                  : `translate(-50%, -50%) translate(${at.x + 40}px, ${at.y}px)`,
            }}
          >
            {data.label}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
