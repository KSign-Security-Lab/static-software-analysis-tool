"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";

import { NODE_H, NODE_W, type GraphNodeData } from "@/lib/trace/layout";
import { cn } from "@/lib/utils";

/**
 * One node of the agent's graph.
 *
 * Hovering shows a `+` on the left, which sets a breakpoint before this node --
 * where you are already looking, rather than in a list somewhere else.
 * Clicking it again clears it.
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
  const hidden = "!size-1 !border-0 !bg-line-3 !opacity-0";
  return (
    <>
      <Handle type="target" position={across ? Position.Left : Position.Top} id="in" className={hidden} />
      <Handle type="source" position={across ? Position.Right : Position.Bottom} id="out" className={hidden} />
      <Handle type="target" position={Position.Right} id="right-in" className={hidden} />
      <Handle type="source" position={Position.Right} id="right-out" className={hidden} />
      <Handle type="target" position={Position.Left} id="left-in" className={hidden} />
      <Handle type="source" position={Position.Left} id="left-out" className={hidden} />
      <Handle type="target" position={Position.Top} id="top-in" className={hidden} />
      <Handle type="source" position={Position.Top} id="top-out" className={hidden} />
      <Handle type="target" position={Position.Bottom} id="bottom-in" className={hidden} />
      <Handle type="source" position={Position.Bottom} id="bottom-out" className={hidden} />
    </>
  );
}

/**
 * What kind of box this is.
 *
 * Half the graph is deterministic Python -- `plan` takes the next wave off the
 * queue, `context` assembles the packs, `locate` resolves anchors, `reduce` writes
 * the results, `skip` exists so a join fires once -- and none of them calls a
 * model. They looked identical to the ones that do, and there was no way to tell
 * from the drawing which boxes were agents. Only `triage`, the four specialists,
 * `gather` and `verify` are, and only `gather` holds tools.
 *
 * `agent` and `code` rather than a longer word for either: they go in a box 124px
 * wide, beside the node's own name.
 */
function Tags({ steps, tools, roster }: { steps: string[]; tools: number; roster: boolean }) {
  // The roster arrives with the graph shape. Until it does, saying nothing is
  // right; tagging every node `code` because the answer had not come back would be
  // a lie rather than a gap.
  if (!roster) return null;

  const agent = steps.length > 0;
  return (
    <span className="flex items-center gap-1">
      <span
        className={cn(
          "rounded-sm px-1 font-mono text-2xs leading-tight",
          agent ? "bg-accent-wash text-accent-ink" : "bg-surface-3 text-ink-faint",
        )}
      >
        {agent ? "agent" : "code"}
      </span>
      {tools > 0 && (
        <span className="rounded-sm bg-surface-3 px-1 font-mono text-2xs leading-tight text-alt">{tools} tools</span>
      )}
      {/* Only where it says something the node's own name does not: `memory` runs
          `lens:memory`, which is the same fact twice. No node runs more than one
          step today -- `gather` was the last and it has a box now -- so this is
          for the next one that does rather than for anything on screen. */}
      {steps.length > 1 && (
        <span className="min-w-0 truncate font-mono text-2xs text-ink-faint">{steps.join(" · ")}</span>
      )}
    </span>
  );
}

export default function StepNode({ data, selected }: NodeProps<Node<GraphNodeData>>) {
  const { name, terminal, visits, averageMs, running, queued, before, after, steps, tools, roster, across, onInterrupt } =
    data;

  // The size is inline, from the same constants dagre laid out against.
  // Expressing it as a utility class instead is how the two drift and the
  // nodes end up overlapping by exactly the difference.
  const size = { width: NODE_W, height: NODE_H };

  if (terminal) {
    return (
      <div
        style={{ width: NODE_W, height: 26 }}
        className="grid place-items-center rounded-full border border-dashed border-line-3 bg-surface font-mono text-2xs text-ink-faint"
      >
        <Ports across={across} />
        {name.replaceAll("__", "")}
      </div>
    );
  }

  return (
    <div
      style={size}
      className={cn(
        "group/node relative flex items-center rounded-md border px-2 py-1.5 transition-colors",
        "border-line-2 bg-surface-2 text-ink-muted",
        visits > 0 && "border-line-3 text-ink",
        queued && "border-warn/60 bg-warn-wash",
        running > 0 && "border-accent bg-accent-wash text-ink-strong shadow-pane",
        (before || after) && "ring-1 ring-alt",
        selected && "border-accent-ink ring-2 ring-accent-ink",
      )}
    >
      <Ports across={across} />

      <button
        type="button"
        aria-label={before ? `${name} 앞의 중단점 해제` : `${name} 앞에 중단점 추가`}
        onClick={(event) => {
          event.stopPropagation();
          onInterrupt?.(name, "before");
        }}
        className={cn(
          "absolute top-1/2 -left-2.5 z-10 grid size-5 -translate-y-1/2 place-items-center rounded-full border text-2xs leading-none",
          "transition-opacity",
          before
            ? "border-alt bg-alt text-bg opacity-100"
            : "border-line-3 bg-surface text-ink-faint opacity-0 group-hover/node:opacity-100 focus-visible:opacity-100",
        )}
      >
        {before ? "■" : "+"}
      </button>

      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="truncate text-xs font-medium">{name}</span>
        <Tags steps={steps} tools={tools} roster={roster} />
        {(running > 0 || queued || visits > 0) && (
          <span className="truncate font-mono text-2xs text-ink-faint">
            {/* The count is the point: "4 running" is a wave of specialists;
                "running" alone reads like the one node this always was. */}
            {running > 1 ? `${running} running` : running === 1 ? "running" : queued ? "queued" : `${visits}×`}
            {averageMs !== null && running === 0 && !queued ? ` · ${duration(averageMs)}` : ""}
          </span>
        )}
      </span>

      {after && <span title={`${name} 뒤의 중단점`} className="absolute -right-1 bottom-1 size-2 rounded-full bg-alt" />}
    </div>
  );
}
