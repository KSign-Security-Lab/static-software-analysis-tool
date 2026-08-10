"use client";

import { useEffect, useMemo } from "react";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import DockTabs from "@/components/workbench/DockTabs";
import KnowledgePanel from "@/features/knowledge/KnowledgePanel";
import { fromAgent } from "@/lib/model/finding";
import { useFindings, useRun } from "@/lib/run/queries";
import { useRunStream } from "@/lib/run/stream";
import { useCheckpoints, useResume, useSpans, useThreads } from "@/lib/run/trace-queries";
import { useRunId } from "@/lib/run/use-run-id";
import { parseAsStringLiteral, useQueryState } from "nuqs";
import ConversationView from "../trace/ConversationView";
import ProblemsPanel from "./ProblemsPanel";
import SpanTree from "../trace/SpanTree";
import StatePanel from "../trace/StatePanel";
import { useFullState, useScopedNode, useSelectedCheckpoint, useSelectedSpan } from "../trace/state";
import { useCentreView, useInspectorView, useOpenFile, useSelectedFinding } from "./state";

const VIEWS = ["tree", "chat"] as const;

/**
 * Everything about the run, under whichever centre view is showing.
 *
 * One dock for both halves of the surface: 문제 is what the agent concluded,
 * 호출 기록 and 상태 단계 are how it got there. They were split across two
 * routes and duplicated 문제 and 구조 지도 between them, which is the clearest
 * sign they were one panel all along.
 */
export default function AgentDock() {
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
  const [, setCentre] = useCentreView();
  const [, setInspector] = useInspectorView();

  const { live, phase, ensureAttached } = useRunStream();
  const spans = useSpans(runId);
  const threads = useThreads(runId);
  const checkpoints = useCheckpoints(runId, full);
  const findings = useFindings(runId);
  const run = useRun(runId);
  const resume = useResume(runId, ensureAttached);

  // Memoised because the effect below depends on it: `?? []` is a fresh array
  // every render, which would re-run the landing effect forever.
  const rows = useMemo(() => spans.data?.spans ?? [], [spans.data]);
  // Started, but nothing recorded yet. Landing here straight off 검사 실행 is
  // the normal way to see this, and it is a different thing from an idle run.
  const starting = phase === "running" || phase === "starting";
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
      scope="agent"
      tabs={[
        {
          id: "problems",
          label: "문제",
          badge: ui.length || undefined,
          content: (
            <ProblemsPanel
              findings={ui}
              selectedId={findingId}
              emptyHint={
                !runId
                  ? "코드를 넣고 ‘검사 실행’을 누르세요."
                  : starting
                    ? "검사 중… 결과는 도착하는 대로 나타납니다."
                    : run.data?.started
                      ? "이 실행에서 발견된 결과가 없습니다."
                      : "아직 검사하지 않았습니다. 위 ‘검사 실행’을 누르세요."
              }
              onSelect={(finding) => {
                void setFindingId(finding.id);
                void setInspector("finding");
                // A finding is a claim about a line, so show the line.
                void setCentre("code");
                if (finding.primary.file) void setPath(finding.primary.file);
              }}
            />
          ),
        },
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
                  <SpanTree
                    spans={rows}
                    selected={spanId}
                    node={node}
                    waiting={starting}
                    onSelect={(id) => {
                      void setSpanId(id);
                      void setInspector("span");
                    }}
                  />
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
              waiting={starting}
              onSelect={(id) => void setCheckpointId(id)}
              onFull={(next) => void setFull(next)}
              onFork={(id, values) => resume.mutate({ checkpointId: id, values })}
              onRerun={(id) => resume.mutate({ checkpointId: id })}
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
