"use client";

import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import { Boxes, FileCode, FunctionSquare } from "lucide-react";

import { KNOWLEDGE_NODE_H, KNOWLEDGE_NODE_W, type KnowledgeNodeData } from "@/lib/trace/knowledge-layout";
import { SEVERITY_DOT } from "@/lib/model/finding";
import { cn } from "@/lib/utils";

const ICON = { file: FileCode, unit: FunctionSquare, community: Boxes };

/**
 * One unit, file or community of the code.
 *
 * Painted twice over: a severity dot from the findings on this chunk, and a
 * progress tint from where the inspection currently is. The second is what the
 * pipeline canvas structurally cannot show -- it says which *node of the
 * agent* is running, this says which part of *your code* it is running on.
 */
export default function KnowledgeNode({ data }: NodeProps<Node<KnowledgeNodeData>>) {
  const Icon = ICON[data.kind];

  return (
    <div
      style={{ width: KNOWLEDGE_NODE_W, height: KNOWLEDGE_NODE_H }}
      className={cn(
        "flex items-center gap-1.5 rounded-md border px-2 transition-colors",
        "border-line-2 bg-surface-2",
        data.progress === "pending" && "border-warn/50 bg-warn-wash",
        data.progress === "running" && "border-accent bg-accent-wash",
        data.selected && "border-accent-ink ring-2 ring-accent-ink",
      )}
    >
      <Handle type="target" position={Position.Left} className="!size-1 !border-0 !bg-line-3 !opacity-0" />
      <Handle type="source" position={Position.Right} className="!size-1 !border-0 !bg-line-3 !opacity-0" />

      <Icon className="size-3.5 shrink-0 text-ink-faint" />

      <span className="min-w-0 flex-1">
        <span className="block truncate text-2xs font-medium text-ink">{data.label}</span>
        <span className="block truncate font-mono text-[10px] text-ink-faint">
          {data.kind === "community" ? `${data.members}개 단위` : data.file}
        </span>
      </span>

      {data.findings > 0 && (
        <span className="flex shrink-0 items-center gap-1" title={`${data.findings}건`}>
          <span className={cn("size-1.5 rounded-full", SEVERITY_DOT[data.severity ?? "info"])} />
          <span className="font-mono text-[10px] text-ink-faint">{data.findings}</span>
        </span>
      )}
    </div>
  );
}
