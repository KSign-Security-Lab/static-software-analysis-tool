"use client";

import { useEffect, useMemo } from "react";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import DockTabs from "@/components/workbench/DockTabs";
import KnowledgePanel from "@/features/knowledge/KnowledgePanel";
import { fromAgent } from "@/lib/model/finding";
import { useFindings } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useCheckpoints, useResume, useSpans, useThreads } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import ConversationView from "./ConversationView";
import ProblemsPanel from "../agent/ProblemsPanel";
import SpanTree from "./SpanTree";
import StatePanel from "./StatePanel";
import { useFullState, useScopedNode, useSelectedCheckpoint, useSelectedSpan } from "./state";
import { useOpenFile, useSelectedFinding } from "../agent/state";

const VIEWS = ["tree", "chat"] as const;

/** TRACE, STATE, PROBLEMS and the structure map, under the graph. */
export default function TraceDock() {
  const [runId] = useRunId();
  const [spanId, setSpanId] = useSelectedSpan();
  const [node] = useScopedNode();
  const [checkpointId, setCheckpointId] = useSelectedCheckpoint();
  const [full, setFull] = useFullState();
  const [view, setView] = useQueryState(
    "record",
    parseAsStringLiteral(VIEWS).withDefault("tree").withOptions({ history: "replace" }),
  );

  const [, setPath] = useOpenFile();
  const [findingId, setFindingId] = useSelectedFinding();

  const { live, phase, ensureAttached } = useRunStream();
  const spans = useSpans(runId);
  const threads = useThreads(runId);
  const checkpoints = useCheckpoints(runId, full);
  const findings = useFindings(runId);
  const resume = useResume(runId, ensureAttached);

  // Memoised because the effect below depends on it: `?? []` is a fresh array
  // every render, which would re-run the landing effect forever.
  const rows = useMemo(() => spans.data?.spans ?? [], [spans.data]);
  const ui = useMemo(() => fromAgent(findings.data?.findings ?? []), [findings.data]);

  // Land on the first model call: it is what someone opening a run wants to
  // read, and the only kind of span that can be tuned.
  useEffect(() => {
    if (spanId || rows.length === 0) return;
    const first = rows.find((span) => span.kind === "llm");
    if (first) void setSpanId(first.id);
  }, [spanId, rows, setSpanId]);

  return (
    <DockTabs
      scope="trace"
      tabs={[
        {
          id: "trace",
          label: "호출 기록",
          badge: spans.data?.summary.spans || undefined,
          content: (
            <div className="flex h-full min-h-0 flex-col">
              <div className="flex shrink-0 items-center gap-2 border-b border-line px-2.5 py-1.5">
                <ToggleGroup
                  type="single"
                  size="sm"
                  variant="outline"
                  value={view}
                  onValueChange={(next) => next && void setView(next as (typeof VIEWS)[number])}
                >
                  <ToggleGroupItem value="tree" className="h-7 px-2 text-2xs">
                    호출 순서
                  </ToggleGroupItem>
                  <ToggleGroupItem value="chat" className="h-7 px-2 text-2xs">
                    대화로 보기
                  </ToggleGroupItem>
                </ToggleGroup>
                {spans.data && (
                  <span className="ml-auto flex items-center gap-2 font-mono text-2xs text-ink-faint">
                    <span>{spans.data.summary.llm_calls} 모델</span>
                    <span>{spans.data.summary.tool_calls} 도구</span>
                    {spans.data.summary.errors > 0 && (
                      <span className="text-danger">{spans.data.summary.errors} 오류</span>
                    )}
                  </span>
                )}
              </div>
              <div className="min-h-0 flex-1">
                {view === "tree" ? (
                  <SpanTree spans={rows} selected={spanId} node={node} onSelect={(id) => void setSpanId(id)} />
                ) : (
                  <ConversationView threads={threads.data?.threads ?? []} node={node} />
                )}
              </div>
            </div>
          ),
        },
        {
          id: "state",
          label: "상태 단계",
          badge: checkpoints.data?.checkpoints.length || undefined,
          content: (
            <StatePanel
              checkpoints={checkpoints.data?.checkpoints ?? []}
              selected={checkpointId ?? live.checkpointId}
              full={full}
              busy={resume.isPending}
              interrupted={phase === "paused"}
              onSelect={(id) => void setCheckpointId(id)}
              onFull={(next) => void setFull(next)}
              onFork={(id, values) => resume.mutate({ checkpointId: id, values })}
              onRerun={(id) => resume.mutate({ checkpointId: id })}
            />
          ),
        },
        {
          id: "problems",
          label: "문제",
          badge: ui.length || undefined,
          content: (
            <ProblemsPanel
              findings={ui}
              selectedId={findingId}
              emptyHint="이 실행에서 발견된 결과가 없습니다."
              onSelect={(finding) => {
                void setFindingId(finding.id);
                if (finding.primary.file) void setPath(finding.primary.file);
              }}
            />
          ),
        },
        {
          id: "graph",
          label: "구조 지도",
          content: <KnowledgePanel />,
        },
      ]}
    />
  );
}
