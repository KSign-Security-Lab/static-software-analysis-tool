"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { createElement } from "react";
import {
  Archive,
  Aperture,
  Boxes,
  Compass,
  Crosshair,
  Filter,
  ListChecks,
  Search,
  ShieldCheck,
  SkipForward,
  type LucideIcon,
} from "lucide-react";

import { NODE_H, NODE_W, type GraphNodeData } from "@/lib/trace/layout";
import { cn } from "@/lib/utils";

/**
 * One node of the agent's graph: a puck, and its name beside it.
 *
 * The label is outside the shape rather than inside it, which is the one decision
 * everything else here follows from. Inside, the box has to be as wide as the
 * longest thing it holds and as tall as the most lines -- and this graph is ten
 * ranks deep, so every pixel of height was a pixel off the zoom the whole drawing
 * gets fitted to. It fitted at 0.3, where a 124x64 box rendered 37x19 and none of
 * the five states it carried could be seen at all.
 *
 * A puck is a fixed 40px whatever it has to say, the two lines of text sit beside
 * it in a column that costs width -- which top to bottom is paid for six times,
 * not ten -- and the state lives on the puck's ring where it is one mark rather
 * than a border, a background and a shadow competing on one box.
 *
 * Hovering shows a `+` on the puck's rim, which sets a breakpoint before this node
 * -- where you are already looking, rather than in a list somewhere else. Clicking
 * it again clears it.
 */

function duration(ms: number | null): string {
  if (ms === null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

/**
 * A glyph per node, as the reference gives every node one.
 *
 * By name, with a fallback per kind, rather than by kind alone: `verify` and
 * `gather` do very different things and two nodes wearing one icon is a drawing
 * that has stopped distinguishing them. The fallback is what makes the map safe --
 * a node this build has not heard of gets the right icon for its kind rather than
 * a hole.
 */
const ICON: Record<string, LucideIcon> = {
  plan: ListChecks,
  context: Boxes,
  triage: Filter,
  scout: Compass,
  skip: SkipForward,
  locate: Crosshair,
  gather: Search,
  verify: ShieldCheck,
  reduce: Archive,
};

function iconFor(name: string, agent: boolean): LucideIcon {
  // Every specialist is `lens:<something>`, and they share a job: look at the
  // unit through one kind of flaw. One icon for the five of them is correct.
  return ICON[name] ?? (agent ? Aperture : Boxes);
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

export default function StepNode({ data, selected }: NodeProps<Node<GraphNodeData>>) {
  const { name, label, terminal, visits, averageMs, running, queued, before, after } = data;
  const { steps, tools, roster, across, onInterrupt, faded, lit, members, litMembers, exits } = data;
  const group = (members?.length ?? 0) > 1;

  // The size is inline, from the same constants dagre laid out against.
  // Expressing it as a utility class instead is how the two drift and the
  // nodes end up overlapping by exactly the difference.
  const size = { width: NODE_W, height: NODE_H };

  if (terminal) {
    return (
      <div
        style={{ width: NODE_W, height: 24 }}
        className="grid place-items-center rounded-full border border-dashed border-line-3 bg-surface font-mono text-2xs text-ink-faint"
      >
        <Ports across={across} />
        {name.replaceAll("__", "")}
      </div>
    );
  }

  // Half the graph is deterministic Python -- `plan` takes the next wave off the
  // queue, `context` assembles the packs, `locate` resolves anchors, `reduce`
  // writes the results, `skip` exists so a join fires once -- and none of them
  // calls a model. Only `triage`, the specialists, `gather` and `verify` do. The
  // roster arrives with the graph shape; until it does, a node tagged `code`
  // because the answer had not come back would be a lie rather than a gap.
  const agent = roster && steps.length > 0;
  const busy = running > 0;

  // How far along, in the corner of the title line. Kept off the mono line
  // because that one is identity -- what this node is called and what it holds --
  // and identity does not change as a run moves.
  const stat = busy
    ? // The count is the point: "4 running" is a wave of specialists; "running"
      // alone reads like the one node this always was.
      running > 1
      ? `${running} 실행`
      : "실행 중"
    : queued
      ? "대기"
      : visits > 0
        ? `${visits}×`
        : "";

  return (
    <div
      style={size}
      className={cn(
        "group/node relative flex items-center gap-2.5 transition-opacity",
        // Not part of the argument being read. See `path` on StepGraph -- the
        // trail is drawn in accent, and this is what makes the accent read.
        faded && "opacity-45",
      )}
    >
      <Ports across={across} />

      {/* A second disc behind the first, so a box standing in for five reads as
          more than one thing before its label is read. Cheaper than drawing five
          and truer than drawing one. */}
      {group && (
        <span
          aria-hidden
          className="absolute top-1 left-1.5 size-10 rounded-full bg-surface-2 ring-1 ring-line-2"
        />
      )}

      <span
        className={cn(
          "relative grid size-10 shrink-0 place-items-center transition-colors",
          "bg-surface-2 text-ink-faint ring-1 ring-line-2",
          // Round is an agent, square is plain Python. The two used to be told
          // apart by an `agent` / `code` word in the box, which is unambiguous
          // and does not fit: the label is outside the shape now and the text
          // column is 110px, which `gather · agent · 4 tools` overruns by half.
          //
          // Not left to a legend either. The overlay's rail lists every node
          // under 에이전트 and 코드 headings with these same two shapes beside
          // them, so the distinction is taught by a list somebody is using
          // anyway rather than by a key they have to go and read. `NodeCard`
          // still spells the word out for whichever node is selected.
          agent ? "rounded-full bg-surface-3" : "rounded-md",
          visits > 0 && "text-ink-muted ring-line-3",
          queued && "ring-warn/60",
          // The one puck the eye should land on: the reference fills its live
          // node and rings it in light, and everything else on the canvas is a
          // dark disc with a hairline.
          busy && "bg-accent-wash text-accent-ink shadow-[0_0_0_6px_var(--accent-wash)] ring-2 ring-accent",
          lit && !busy && "text-accent-ink ring-2 ring-accent",
          selected && "ring-2 ring-accent-ink",
        )}
      >
        {/* `createElement` rather than binding the lookup to a capitalised
            local: the references are module-level constants and stable, but
            `const Icon = iconFor(...)` is indistinguishable from defining a
            component inside a render, and the lint rule that catches the real
            version of that mistake cannot tell the two apart. */}
        {createElement(iconFor(name, agent), { className: "size-4" })}

        {/* Not on the group: a breakpoint is compiled in by node name, and the
            group is not a node the agent has ever heard of. Expand it and the
            five real ones each get their own. */}
        {onInterrupt && (
          <button
            type="button"
            aria-label={before ? `${name} 앞의 중단점 해제` : `${name} 앞에 중단점 추가`}
            onClick={(event) => {
              event.stopPropagation();
              onInterrupt(name, "before");
            }}
            className={cn(
              "absolute -top-1 -left-1 z-10 grid size-4 place-items-center rounded-full border text-2xs leading-none",
              "transition-opacity",
              before
                ? "border-alt bg-alt text-bg opacity-100"
                : "border-line-3 bg-surface text-ink-faint opacity-0 group-hover/node:opacity-100 focus-visible:opacity-100",
            )}
          >
            {before ? "■" : "+"}
          </button>
        )}

        {after && (
          <span
            title={`${name} 뒤의 중단점`}
            className="absolute -right-0.5 -bottom-0.5 size-2 rounded-full bg-alt ring-2 ring-surface"
          />
        )}

        {/* The run can stop here. It used to be an `__end__` box two ranks away
            with the longest edge on the canvas pointing at it; the condition
            lives on this node, so the fact does too.

            On the rim rather than in the text: as a chip beside the title it
            competed with the visit count and truncated `차례 고르기` to
            `차례 고...`, and on the mono line it pushed the node's own name off
            the end. A mark costs no characters. */}
        {exits && (
          <span
            title="여기서 검사가 끝날 수 있습니다"
            aria-hidden
            className="absolute -top-0.5 -right-0.5 size-2 rounded-full border border-line-3 bg-surface"
          />
        )}
      </span>

      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex min-w-0 items-baseline gap-1.5">
          <span
            className={cn(
              "min-w-0 truncate text-xs leading-tight font-medium text-ink-muted",
              visits > 0 && "text-ink",
              (busy || selected || lit) && "text-ink-strong",
            )}
          >
            {label}
          </span>
          {stat && (
            <span className={cn("shrink-0 text-2xs leading-tight text-ink-faint", busy && "text-accent-ink")}>
              {stat}
            </span>
          )}
        </span>

        {/* The machine name stays: it is what the breakpoint list, the trace and
            every error message call this thing, and a drawing that only spoke
            Korean would not be findable from any of them.

            The tool count stays with it because it is a fact about what the node
            *is*, and because the drawing saying `10 tools` without saying which
            is what once sent somebody looking for a `RAG` box that cannot exist.
            Which tools they are is in the node panel.

            The group says what it stands in for instead. Named rather than
            counted when a claim trail runs through one of them -- `memory` is the
            answer to "which specialist found this", and `렌즈 5` is not. */}
        <span className="truncate font-mono text-2xs leading-tight text-ink-faint">
          {group ? (
            (litMembers?.length ?? 0) > 0 ? (
              <span className="text-accent-ink">{litMembers!.join(" · ")}</span>
            ) : (
              `렌즈 ${members!.length}`
            )
          ) : (
            <>
              {name}
              {tools > 0 ? ` · 도구 ${tools}` : ""}
              {!busy && !queued && visits > 0 && averageMs !== null ? ` · ${duration(averageMs)}` : ""}
            </>
          )}
        </span>
      </span>
    </div>
  );
}
