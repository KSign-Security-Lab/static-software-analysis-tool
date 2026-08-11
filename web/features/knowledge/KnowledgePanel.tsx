"use client";

import dynamic from "next/dynamic";
import { useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api/client";
import { SEVERITY_DOT, countByChunk, fromAgent } from "@/lib/model/finding";
import { useKnowledge } from "@/lib/run/knowledge-queries";
import { useFindings } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useRunId } from "@/lib/run/use-run-id";
import { DRAW_LIMIT } from "@/lib/trace/knowledge-layout";
import { cn } from "@/lib/utils";
import { useOpenFile, useSelectedFinding } from "@/lib/run/selection";

// React Flow measures the DOM, so this one is client-only too.
const KnowledgeGraphView = dynamic(() => import("@/components/graph/KnowledgeGraphView"), {
  ssr: false,
  loading: () => (
    <div className="grid h-full place-items-center p-4">
      <Skeleton className="h-20 w-1/2" />
    </div>
  ),
});

/**
 * The code's own structure, and where the run is inside it.
 *
 * The endpoint has existed since the agent gained an index and never had a
 * client. Node ids are chunk ids, so this joins straight onto findings and
 * onto the inspection's pending/running channels -- which is what makes it the
 * run's spatial index rather than a decorative picture.
 */
export default function KnowledgePanel() {
  const [runId] = useRunId();
  const [, setPath] = useOpenFile();
  const [, setFindingId] = useSelectedFinding();
  const { live } = useRunStream();

  const knowledge = useKnowledge(runId);
  const findings = useFindings(runId);
  const [selected, setSelected] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());

  const counts = useMemo(() => countByChunk(fromAgent(findings.data?.findings ?? [])), [findings.data]);
  const running = useMemo(() => new Set(live.wave?.chunks ?? []), [live.wave]);
  const pending = useMemo(() => new Set(live.chunk ? [live.chunk.id] : []), [live.chunk]);

  if (!runId) return <p className="p-4 text-xs text-ink-faint">실행을 선택하면 코드의 구조가 여기 표시됩니다.</p>;

  if (knowledge.isPending) {
    return (
      <div className="space-y-2 p-4">
        <Skeleton className="h-4 w-1/3" />
        <Skeleton className="h-4 w-1/2" />
      </div>
    );
  }

  // A 404 means the run was never indexed. That is an ordinary answer, not a
  // failure -- so it is stated, not raised.
  if (knowledge.error instanceof ApiError && knowledge.error.status === 404) {
    return <p className="p-4 text-xs text-ink-faint">이 실행에는 색인이 없습니다. 파일을 올리면 구조가 만들어집니다.</p>;
  }
  if (knowledge.error || !knowledge.data) {
    return <p className="p-4 text-xs text-danger">구조를 불러오지 못했습니다.</p>;
  }

  const graph = knowledge.data;
  const open = (id: string) => {
    const node = graph.nodes.find((each) => each.id === id);
    if (node?.file) void setPath(node.file);
    void setFindingId(null);
    setSelected(id);
  };

  // Past this, drawing it is a screensaver: the useful question becomes "what
  // groups exist and what is in them", and that is a list.
  if (graph.counts.nodes > DRAW_LIMIT) {
    return (
      <div className="h-full overflow-auto p-2.5">
        <p className="mb-2 text-2xs text-ink-faint">
          {graph.counts.nodes.toLocaleString()}개 단위 · {graph.counts.communities}개 묶음. 그리기에는 너무 커서 목록으로
          보여줍니다.
        </p>
        <ul className="space-y-1">
          {graph.communities.map((community) => (
            <li key={community.id} className="rounded-sm border border-line px-2 py-1.5">
              <div className="flex items-center gap-2">
                <span className="truncate text-xs text-ink">{community.label}</span>
                <Badge variant="outline" className="shrink-0 px-1 py-0 text-2xs font-normal">
                  {community.members.length}
                </Badge>
              </div>
              <p className="truncate font-mono text-2xs text-ink-faint">{community.files.join(", ")}</p>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 items-center gap-2 border-b border-line px-2.5 py-1 text-2xs text-ink-faint">
        <span>{graph.counts.nodes}개 단위</span>
        <span>{graph.counts.edges}개 관계</span>
        <span>{graph.counts.communities}개 묶음</span>
        {graph.counts.inferred > 0 && (
          <span className="flex items-center gap-1">
            <span className="inline-block h-px w-3 border-t border-dashed border-line-3" />
            {graph.counts.inferred}개 추정
          </span>
        )}
        {counts.size > 0 && (
          <span className="ml-auto flex items-center gap-1">
            <span className={cn("size-1.5 rounded-full", SEVERITY_DOT.high)} />
            결과가 있는 단위 {counts.size}
          </span>
        )}
      </div>
      <div className="min-h-0 flex-1">
        <KnowledgeGraphView
          graph={graph}
          counts={counts}
          pending={pending}
          running={running}
          selected={selected}
          expanded={expanded}
          onSelect={(id) => (id ? open(id) : setSelected(null))}
          onExpand={(community) => setExpanded((current) => new Set(current).add(community))}
        />
      </div>
    </div>
  );
}
