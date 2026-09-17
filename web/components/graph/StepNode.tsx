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

function duration(ms: number | null): string {
  if (ms === null) return "";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

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
  return ICON[name] ?? (agent ? Aperture : Boxes);
}

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

  const agent = roster && steps.length > 0;
  const busy = running > 0;

  const stat = busy
    ?
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
        faded && "opacity-45",
      )}
    >
      <Ports across={across} />

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
          agent ? "rounded-full bg-surface-3" : "rounded-md",
          visits > 0 && "text-ink-muted ring-line-3",
          queued && "ring-warn/60",
          busy && "bg-accent-wash text-accent-ink shadow-[0_0_0_6px_var(--accent-wash)] ring-2 ring-accent",
          lit && !busy && "text-accent-ink ring-2 ring-accent",
          selected && "ring-2 ring-accent-ink",
        )}
      >
        {createElement(iconFor(name, agent), { className: "size-4" })}

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
