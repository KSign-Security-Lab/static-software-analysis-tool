"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import type { GraphNodeData } from "@/lib/studio/layout";

/**
 * One node of the graph.
 *
 * Hovering shows a `+` on the left, which sets an interrupt before this node --
 * the way Studio does it, so a breakpoint is set where you are already looking
 * rather than in a menu somewhere else. Clicking it again clears it.
 *
 * The side handles carry the edges that cannot go down the column: the return
 * to `plan` up the right, the exit to `__end__` down the left.
 */

function duration(ms: number | null): string {
  if (ms === null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

/**
 * A port on every side.
 *
 * The steps use the two that face the flow; returns and early exits use the
 * two across it, so neither has to cut through the line of steps between its
 * ends. Which pair is which depends on the direction the graph is laid out in,
 * so all four exist and the layout picks.
 */
function Ports({ across }: { across: boolean }) {
  return (
    <>
      <Handle type="target" position={across ? Position.Left : Position.Top} id="in" className="gx-handle" />
      <Handle type="source" position={across ? Position.Right : Position.Bottom} id="out" className="gx-handle" />
      <Handle type="target" position={Position.Right} id="right-in" className="gx-handle" />
      <Handle type="source" position={Position.Right} id="right-out" className="gx-handle" />
      <Handle type="target" position={Position.Left} id="left-in" className="gx-handle" />
      <Handle type="source" position={Position.Left} id="left-out" className="gx-handle" />
      <Handle type="target" position={Position.Top} id="top-in" className="gx-handle" />
      <Handle type="source" position={Position.Top} id="top-out" className="gx-handle" />
      <Handle type="target" position={Position.Bottom} id="bottom-in" className="gx-handle" />
      <Handle type="source" position={Position.Bottom} id="bottom-out" className="gx-handle" />
    </>
  );
}

export default function GraphNode({ data, selected }: NodeProps<Node<GraphNodeData>>) {
  const { name, terminal, visits, averageMs, running, queued, before, after, across, onInterrupt } = data;

  if (terminal) {
    return (
      <div className="gx-terminal">
        <Ports across={across} />
        {name.replaceAll("__", "")}
      </div>
    );
  }

  const classes = [
    "gx-node",
    visits > 0 ? "is-visited" : "",
    running > 0 ? "is-running" : "",
    queued ? "is-queued" : "",
    before || after ? "is-break" : "",
    selected ? "is-selected" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={classes}>
      <Ports across={across} />

      <button
        type="button"
        className={`gx-add ${before ? "is-on" : ""}`}
        title={before ? "이 노드 앞의 중단점 해제" : "이 노드 앞에 중단점 추가"}
        onClick={(event) => {
          event.stopPropagation();
          onInterrupt?.(name, "before");
        }}
      >
        {before ? "■" : "+"}
      </button>

      <span className="gx-node-body">
        <span className="gx-node-name">{name}</span>
        {(running > 0 || queued || visits > 0) && (
          <span className="gx-node-stat">
            {/* The count is the point: "4 running" is a wave of specialists;
                "running" alone reads like the one node this always was. */}
            {running > 1 ? `${running} running` : running === 1 ? "running" : queued ? "queued" : `${visits}×`}
            {averageMs !== null && running === 0 && !queued ? ` · ${duration(averageMs)}` : ""}
          </span>
        )}
      </span>

      {after && <span className="gx-after" title="이 노드 뒤의 중단점" />}
    </div>
  );
}
