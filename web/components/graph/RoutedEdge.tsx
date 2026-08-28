"use client";

import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath, type Edge, type EdgeProps } from "@xyflow/react";

import { roundedPath } from "@/lib/trace/edge-path";
import type { RoutedEdgeData } from "@/lib/trace/layout";
import { cn } from "@/lib/utils";

/**
 * An edge drawn along the route dagre computed for it, with the word that names it.
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
 * absent from the drawing -- and that fallback is why every edge can be this type
 * now, including the loop, which is not in the dagre graph at all.
 */

/** Halfway along the polyline, by length rather than by index. */
function midpoint(points: { x: number; y: number }[]): { x: number; y: number } {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) total += Math.hypot(points[i].x - points[i - 1].x, points[i].y - points[i - 1].y);

  // By length, not `points[Math.floor(n / 2)]`: dagre emits a point per rank
  // crossed, so the middle *index* of a route that skips four ranks sits wherever
  // the crossings happened to bunch up rather than in the middle of the line.
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
  // Where the return begins, not the middle of it.
  //
  // `reduce -> plan` runs back past the entire drawing, and the lane it takes
  // crosses the rank of six specialists on the way -- so its midpoint is inside
  // a node no matter which way the label is nudged. Its *source* end never is:
  // it is the gap immediately outside the node the return leaves from. Reading
  // 되돌아가기 where the line departs is also the more useful of the two.
  const at = routed ? midpoint(points) : loop ? { x: sourceX, y: sourceY } : { x: stepX, y: stepY };

  return (
    <>
      <BaseEdge
        path={path}
        markerEnd={markerEnd}
        interactionWidth={interactionWidth}
        style={{
          ...style,
          // The chain that produced the finding being read, drawn rather than
          // merely left undimmed. A path you can follow is the whole point of
          // putting the drawing on screen for a finding at all.
          ...(lit ? { stroke: "var(--accent)", strokeWidth: 1.75 } : {}),
        }}
      />

      {data?.label && (
        <EdgeLabelRenderer>
          <div
            // `pointer-events-none`: the pill is a caption, not a target, and a
            // div in this layer sits above the canvas and would eat the drag.
            className={cn(
              "pointer-events-none absolute rounded-full border px-1.5 py-px font-mono text-2xs leading-tight",
              "border-line-2 bg-surface text-ink-faint",
              loop && "border-alt/40 text-alt",
              lit && "border-accent/50 text-accent-ink",
            )}
            style={{
              // Off the line, not on it.
              //
              // Centred on the path, a pill sits in the gap between two ranks --
              // which is 36px wide and holds a 50px pill, so `has_work` printed
              // across the node it came from. Moving it perpendicular to the flow
              // clears every node without needing the gap to grow: up, when the
              // pipeline runs across; to the side, when it runs down.
              //
              // The loop is anchored beside its start instead. It returns past
              // the whole drawing, so its midpoint is the middle of the canvas
              // and no perpendicular offset saves it.
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
